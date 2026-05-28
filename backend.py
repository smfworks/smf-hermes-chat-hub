#!/usr/bin/env python3
"""
Hermes Hub Chat Backend — proxies chat requests to the right hermes profile.

Supports session resume, retry logic, request cancellation, and persistent
session storage so conversations survive backend restarts.

Start with: python3 backend.py
"""

import subprocess, json, time, os, re, shlex, uuid, threading, signal
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from socketserver import ThreadingMixIn
from pathlib import Path

# ── Cross-channel bridge integration ──────────────────────────────────────
BRIDGE_SCRIPT = str(Path.home().parent / "mikesai1" / ".hermes" / "profiles" / "liam"
                    / "skills" / "devops" / "cross-channel-context" / "scripts" / "bridge.py")

# Resolve the real home even when $HOME is overridden
def _real_home() -> Path:
    home = Path.home()
    if ".hermes/profiles/" in str(home):
        import pwd
        try:
            return Path(pwd.getpwuid(os.getuid()).pw_dir)
        except (ImportError, KeyError):
            pass
    return home

REAL_BRIDGE_SCRIPT = str(_real_home() / ".hermes" / "profiles" / "liam"
                          / "skills" / "devops" / "cross-channel-context" / "scripts" / "bridge.py")


def bridge_run(*args: str) -> str | None:
    """Run bridge.py with arguments. Returns stdout on success, None on failure."""
    try:
        result = subprocess.run(
            ["python3", REAL_BRIDGE_SCRIPT, *args],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def bridge_log(user: str, platform: str, target: str, summary: str, profile: str = "liam") -> None:
    """Log a message to the cross-channel bridge (fire-and-forget)."""
    bridge_run("log", "--user", user, "--platform", platform,
               "--target", target, "--summary", summary,
               "--profile", profile)

PORT = 9099
TIMEOUT = 180          # max seconds to wait for a response
MAX_MESSAGE_LEN = 32000 # refuse messages longer than this
MAX_BODY_LEN = 65536    # refuse request bodies larger than this
MAX_RETRIES = 2         # retry transient errors up to this many times
RETRY_DELAY = 2         # seconds between retries (doubles each attempt)
SESSION_STORE = Path.home() / '.hermes-hub-sessions.json'

PROFILES = {
    "default": ["hermes"],
    "drj":     ["hermes", "--profile", "drj"],
    "harry":   ["hermes", "--profile", "harry"],
    "liam":    ["hermes", "--profile", "liam"],
    "naill":   ["hermes", "--profile", "naill"],
    "zayn":    ["hermes", "--profile", "zayn"],
}

# ── Session tracking ──────────────────────────────────────────────────────
# Maps profile_id -> last known session_id
# Persisted to disk so they survive backend restarts.
sessions: dict[str, str] = {}
session_lock = threading.Lock()

# ── In-flight request tracking ────────────────────────────────────────────
# Maps profile_id -> subprocess.Popen (for cancellation)
active_procs: dict[str, subprocess.Popen] = {}
active_procs_lock = threading.Lock()


def load_sessions():
    """Load session state from disk."""
    global sessions
    try:
        if SESSION_STORE.exists():
            data = json.loads(SESSION_STORE.read_text())
            if isinstance(data, dict):
                sessions = {k: v for k, v in data.items() if isinstance(v, str)}
                print(f"   Loaded {len(sessions)} sessions from {SESSION_STORE}")
    except (json.JSONDecodeError, OSError) as e:
        print(f"   Warning: could not load sessions: {e}")


def save_sessions():
    """Persist session state to disk."""
    try:
        with session_lock:
            SESSION_STORE.write_text(json.dumps(sessions, indent=2))
    except OSError as e:
        print(f"   Warning: could not save sessions: {e}")


# ── Output cleaning ────────────────────────────────────────────────────────
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\\]*(?:\x1b\\\\|\x07)|\r')
TUI_FRAMES = re.compile(r'┌─[^┐]*┐.*?╯', re.DOTALL)
PROGRESS_LINES = re.compile(r'^\s*(░|█|▒|▓|╰|╭|├|◆|│|─|┄|┈|╴|╶|╼|╾|╿).*', re.MULTILINE)
BANNER_RE = re.compile(
    r'╭────────────.*?╮.*?╰──────────────────────────────────────╯',
    re.DOTALL
)
SESSION_HINT_RE = re.compile(r'hermes\s+--resume\s+(\S+)')

def clean_output(text: str) -> str:
    """Strip Hermes TUI decorations, ANSI, banners, and progress bars from output."""
    text = BANNER_RE.sub('', text)
    text = ANSI_RE.sub('', text)
    text = re.sub(r'^\s*[┌└┐┘├┤┬┴┼╭╰╮╯─│═╔╚╗╝╠╣╦╩╬].*\n?', '', text, flags=re.MULTILINE)
    text = PROGRESS_LINES.sub('', text)
    text = re.sub(r'^Query:.*\n', '', text, flags=re.MULTILINE)
    text = text.strip()
    return text

def extract_response(text: str) -> tuple[str, str | None]:
    """Extract the agent's response and optional session_id from cleaned output.
    
    Returns (response_text, session_id_or_None).
    """
    session_id = None
    m = SESSION_HINT_RE.search(text)
    if m:
        session_id = m.group(1)

    lines = text.split('\n')
    response_lines = []
    skip_patterns = [
        r'^Session:', r'^Duration:', r'^Messages:', r'^Resume this',
        r'^Initializing', r'^Model:', r'^Provider:', r'^hermes chat',
        r'^│', r'^╭', r'^╰', r'^🔄', r'^⚠', r'^❌', r'^⏳',
        r'hermes --resume', r'🔌\s*Provider', r'🌐\s*Endpoint', r'📝\s*Error',
    ]
    for line in lines:
        skip = False
        for pattern in skip_patterns:
            if re.match(pattern, line) or re.search(pattern, line):
                skip = True
                break
        if not skip and line.strip():
            response_lines.append(line)
    result = '\n'.join(response_lines).strip()
    result = re.sub(r'^\s*hermes --resume \S+\s*', '', result)
    return result, session_id


# ── Health check ───────────────────────────────────────────────────────────
def check_hermes_available() -> bool:
    """Quick check that the hermes binary is on PATH."""
    try:
        result = subprocess.run(
            ['hermes', '--version'], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_chat(profile: str, message: str, session_id: str | None = None) -> dict:
    """Run a hermes chat command and return structured result.
    
    Returns: {
        'response': str,        # The agent's response text
        'session_id': str|None, # Session ID for resume
        'error': str|None,      # Error message if any
        'recoverable': bool,    # Whether retrying might help
        'status': int,          # HTTP status code
    }
    """
    cmd = PROFILES[profile] + ['chat', '-q', message]
    if session_id:
        cmd = PROFILES[profile] + ['--resume', session_id, 'chat', '-q', message]

    proc = None
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        # Track in-flight process for cancellation
        with active_procs_lock:
            active_procs[profile] = proc
        
        try:
            stdout, stderr = proc.communicate(timeout=TIMEOUT + 5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return {
                'response': None,
                'session_id': None,
                'error': f'Request timed out after {TIMEOUT}s. The agent may be stuck — try "New Chat" to reset.',
                'recoverable': True,
                'status': 504,
            }
        finally:
            with active_procs_lock:
                active_procs.pop(profile, None)

        if proc.returncode != 0 and not stdout.strip():
            err = ANSI_RE.sub('', stderr).strip()
            if err:
                # Classify error as recoverable or not
                recoverable = any(
                    kw in err.lower()
                    for kw in ['rate limit', '429', 'too many requests', 'timeout', 'timed out', 'connection', 'network', 'temporary', 'retry']
                )
                return {
                    'response': None,
                    'session_id': None,
                    'error': f'Agent error: {err[:500]}',
                    'recoverable': recoverable,
                    'status': 502,
                }
            return {
                'response': None,
                'session_id': None,
                'error': 'Agent returned empty output',
                'recoverable': True,
                'status': 502,
            }

        cleaned = clean_output(stdout)
        response_text, new_session_id = extract_response(cleaned)

        # Persist session ID
        if new_session_id:
            with session_lock:
                sessions[profile] = new_session_id
            save_sessions()

        if not response_text:
            response_text = '[no response]'

        return {
            'response': response_text,
            'session_id': new_session_id or session_id,
            'error': None,
            'recoverable': False,
            'status': 200,
        }

    except FileNotFoundError:
        return {
            'response': None,
            'session_id': None,
            'error': 'hermes binary not found on PATH',
            'recoverable': False,
            'status': 500,
        }
    except Exception as e:
        return {
            'response': None,
            'session_id': None,
            'error': str(e),
            'recoverable': True,
            'status': 500,
        }
    finally:
        with active_procs_lock:
            if profile in active_procs and active_procs[profile] is proc:
                active_procs.pop(profile, None)


# ── HTTP Handler ───────────────────────────────────────────────────────────
class ChatHandler(BaseHTTPRequestHandler):
    """Handles POST /{profile} for chat and GET /health for health checks."""
    
    def log_message(self, format, *args):
        # Suppress per-request logs -- uncomment for debugging:
        # print(f"[{self.log_date_time_string()}] {format % args}")
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        """Health check and context endpoints."""
        path = urlparse(self.path).path.strip('/')
        if path == 'health':
            healthy = check_hermes_available()
            with session_lock:
                active_profiles = {k: v for k, v in sessions.items()}
            # Check for in-flight requests
            with active_procs_lock:
                busy = list(active_procs.keys())
            self._send_json({
                'status': 'ok' if healthy else 'degraded',
                'hermes': healthy,
                'profiles': list(PROFILES.keys()),
                'sessions': active_profiles if healthy else {},
                'busy': busy,
            })
        elif path.startswith('context'):
            # GET /context?user=michael&minutes=60
            # OR GET /context/{profile}?user=michael&minutes=60
            query = parse_qs(urlparse(self.path).query)
            user = query.get('user', ['michael'])[0]
            minutes = int(query.get('minutes', ['60'])[0])
            lookup_path = path.split('/')
            profile = lookup_path[1] if len(lookup_path) > 1 and lookup_path[1] != 'context' else None

            args = ["lookup", "--user", user, "--minutes", str(minutes), "--count", "10"]
            if profile:
                args += ["--profile", profile]

            result = bridge_run(*args)
            if result:
                try:
                    data = json.loads(result)
                    self._send_json(data)
                except json.JSONDecodeError:
                    self._send_json({'count': 0, 'messages': [], 'error': 'Bridge returned non-JSON'})
            else:
                self._send_json({'count': 0, 'messages': [], 'error': 'Bridge unavailable'})
        else:
            self._send_json({'error': 'Not found. Use POST /{profile} to chat.'}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.strip('/')

        # Health check via POST too
        if path == 'health':
            self.do_GET()
            return

        if path not in PROFILES:
            self._send_json({'error': f'Unknown profile: {path}. Available: {", ".join(PROFILES.keys())}'}, 404)
            return

        # Read body with size cap
        length = int(self.headers.get('Content-Length', 0))
        if length > MAX_BODY_LEN:
            self._send_json({'error': 'Request too large'}, 413)
            return
        body = self.rfile.read(length) if length else b''
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json({'error': 'Invalid JSON'}, 400)
            return

        message = data.get('message', '').strip()
        if not message:
            self._send_json({'error': 'No message provided'}, 400)
            return
        if len(message) > MAX_MESSAGE_LEN:
            self._send_json({'error': f'Message too long (max {MAX_MESSAGE_LEN} chars)'}, 400)
            return

        # Check if there's already a request in flight for this profile
        with active_procs_lock:
            if path in active_procs:
                self._send_json({
                    'error': 'A request is already in progress for this agent. Please wait or cancel it.',
                    'recoverable': True,
                }, 429)
                return

        # Get stored session ID for resume
        with session_lock:
            session_id = sessions.get(path)
        
        # Try with retries for recoverable errors
        last_result = None
        for attempt in range(MAX_RETRIES + 1):
            result = run_chat(path, message, session_id)
            
            if result['error'] is None:
                # Success! Log to cross-channel bridge
                response_preview = result['response'][:120].replace('\n', ' ')
                bridge_log(
                    user="michael", platform="web", target=f"hub:{path}",
                    summary=f"Hub ({path}): {response_preview}",
                    profile=path,
                )
                self._send_json({
                    'response': result['response'],
                    'session_id': result['session_id'],
                })
                return
            
            last_result = result
            
            if not result['recoverable'] or attempt == MAX_RETRIES:
                # Non-recoverable or out of retries
                break
            
            # Wait before retrying
            delay = RETRY_DELAY * (2 ** attempt)
            time.sleep(delay)
        
        # All retries exhausted or non-recoverable error
        self._send_json({
            'error': last_result['error'],
            'recoverable': last_result['recoverable'],
            'retries_remaining': 0,
        }, last_result['status'])

    def do_DELETE(self):
        """Clear session for a profile, or cancel an in-flight request."""
        parsed = urlparse(self.path)
        path = parsed.path.strip('/')
        
        # Cancel in-flight request
        if path.startswith('cancel/'):
            profile = path[len('cancel/'):]
            if profile not in PROFILES:
                self._send_json({'error': f'Unknown profile: {profile}'}, 404)
                return
            with active_procs_lock:
                proc = active_procs.pop(profile, None)
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()
                self._send_json({'status': 'cancelled', 'profile': profile})
            else:
                self._send_json({'status': 'no_active_request', 'profile': profile})
            return
        
        # Clear sessions
        if path == 'sessions':
            with session_lock:
                sessions.clear()
            save_sessions()
            self._send_json({'status': 'cleared', 'message': 'All sessions cleared'})
        elif path in PROFILES:
            with session_lock:
                removed = sessions.pop(path, None)
            save_sessions()
            self._send_json({
                'status': 'cleared',
                'profile': path,
                'had_session': removed is not None,
            })
        else:
            self._send_json({'error': f'Unknown profile: {path}'}, 404)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests concurrently — one thread per request."""
    daemon_threads = True
    allow_reuse_address = True


# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Load persisted sessions
    load_sessions()
    
    hermes_ok = check_hermes_available()
    print(f"🚀 Hermes Hub Chat Backend on http://0.0.0.0:{PORT}")
    print(f"   Profiles: {', '.join(PROFILES.keys())}")
    print(f"   Hermes:   {'✅ found' if hermes_ok else '❌ not on PATH'}")
    print(f"   Sessions: {len(sessions)} restored from {SESSION_STORE}")
    print(f"   Endpoints: GET /health | POST /<profile> | DELETE /<profile> | DELETE /sessions | DELETE /cancel/<profile>")
    
    server = ThreadedHTTPServer(('0.0.0.0', PORT), ChatHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down — saving sessions...")
        save_sessions()
        server.shutdown()
        server.server_close()