# Hermes Hub

A resilient web chat interface for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — chat with multiple AI agent profiles from a browser, with auto-retry, session persistence, request cancellation, and Tailscale remote access.

![Hermes Hub](https://img.shields.io/badge/status-production-green) ![Python](https://img.shields.io/badge/python-3.10+-blue) ![License](https://img.shields.io/badge/license-MIT-orange)

## What It Does

Hermes Hub provides a clean web UI to chat with Hermes Agent profiles. Each agent (e.g., "Liam", "Dr J", "Harry") gets its own chat card, and conversations are automatically resumed across messages using `hermes --resume`.

```
┌─────────────────────────────────────────────────────────┐
│  ⚡ Hermes Hub                                          │
│                                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐               │
│  │ Default │  │  Dr J   │  │  Harry  │               │
│  │    H    │  │    J    │  │    H    │               │
│  └─────────┘  └─────────┘  └─────────┘               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐               │
│  │  Liam   │  │  Naill  │  │  Zayn   │               │
│  │    L    │  │    N    │  │    Z    │               │
│  └─────────┘  └─────────┘  └─────────┘               │
└─────────────────────────────────────────────────────────┘
```

## Architecture

```
Browser (index.html)
    │
    │  POST /{profile}  { message: "..." }
    │  DELETE /cancel/{profile}
    │  GET /health
    │  DELETE /{profile}  (clear session)
    │
    ▼
Backend (backend.py) ─── Python HTTP server on port 9099
    │
    │  hermes --profile {profile} chat -q "..."
    │  hermes --profile {profile} --resume {session_id} chat -q "..."
    │
    ▼
Hermes Agent CLI ─── Subprocess per message, stdout captured
```

The backend is intentionally simple: each chat message spawns a `hermes chat` subprocess, captures the output, strips TUI decorations, and returns the clean response. Session IDs are extracted from the output and stored for conversation continuity.

### Resilience Features

| Feature | Description |
|---------|-------------|
| **Session persistence** | Conversations survive backend restarts — sessions saved to `~/.hermes-hub-sessions.json` |
| **Auto-retry** | Transient errors (rate limits, timeouts) are retried up to 2x with exponential backoff |
| **Request cancellation** | Cancel button kills both the frontend fetch and backend subprocess |
| **Error classification** | Backend marks errors as `recoverable` or permanent; frontend auto-retries recoverable ones |
| **Health monitoring** | Periodic health checks (every 30s) with status indicator |
| **Retry button** | Failed messages show an inline retry button — no need to retype |
| **Concurrent protection** | Returns 429 if a request is already in flight for a profile |

## Quick Start

### Prerequisites

- Python 3.10+
- [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed and configured (`hermes` on PATH)
- One or more Hermes profiles set up

### 1. Clone and Run

```bash
git clone https://github.com/smfworks/smf-hermes-chat-hub.git
cd smf-hermes-chat-hub

# Start the backend
python3 backend.py
```

### 2. Serve the Frontend

```bash
# Option A: Simple HTTP server (included in the start script)
python3 -m http.server 9100

# Option B: Use the start script (runs both)
python3 start.py
```

### 3. Open in Browser

```
http://localhost:9100        # Local access
http://100.x.x.x:9100       # Tailscale access (see Remote Access below)
```

## Configuration

### Agent Profiles

Edit the `PROFILES` dictionary in `backend.py` to match your Hermes profiles:

```python
PROFILES = {
    "default": ["hermes"],
    "my-agent": ["hermes", "--profile", "my-agent"],
}
```

Each entry maps a short ID (used in the URL and UI) to the `hermes` CLI command with the appropriate `--profile` flag.

### Frontend Agent Cards

Edit the `agents` array in `index.html` to match:

```javascript
const agents = [
  { id: "default", name: "Default", emoji: "H", model: "deepseek-v4-pro", color: "c1", badge: "default" },
  { id: "my-agent", name: "My Agent", emoji: "M", model: "your-model", color: "c2", badge: "" },
];
```

- `id` must match the key in `PROFILES`
- `color` maps to CSS classes `c1` through `c6`
- `badge` shows as a small label on the card; use `"default"` for the primary agent, `""` for none

### Timeout and Limits

```python
TIMEOUT = 180           # Max seconds to wait for a response per message
MAX_MESSAGE_LEN = 32000 # Max message length in characters
MAX_BODY_LEN = 65536    # Max request body size in bytes
MAX_RETRIES = 2         # Auto-retry count for transient errors
RETRY_DELAY = 2         # Seconds between retries (doubles each attempt)
```

## API Reference

### `POST /{profile}`

Send a message to an agent profile.

**Request:**
```json
{ "message": "Hello, agent!" }
```

**Response (success):**
```json
{ "response": "Hello! How can I help?", "session_id": "abc123" }
```

**Response (error):**
```json
{ "error": "Agent error: rate limit exceeded", "recoverable": true }
```

The `recoverable` field tells the frontend whether auto-retry is appropriate. Transient errors (rate limits, timeouts, connection issues) return `"recoverable": true`. Permanent errors (binary not found, invalid profile) return `"recoverable": false`.

### `GET /health`

Returns backend status and Hermes availability.

```json
{
  "status": "ok",
  "hermes": true,
  "profiles": ["default", "drj", "harry", "liam", "naill", "zayn"],
  "sessions": { "liam": "abc123" },
  "busy": []
}
```

### `DELETE /{profile}`

Clear the session for a specific profile, starting a fresh conversation.

### `DELETE /sessions`

Clear all sessions across all profiles.

### `DELETE /cancel/{profile}`

Cancel an in-flight request for a profile. Kills the backend subprocess and returns immediately.

## Remote Access via Tailscale

Hermes Hub is designed to be accessed from your phone or any device on your Tailscale network. No VPN configuration, no port forwarding, no HTTPS certificates needed — Tailscale handles encryption and authentication.

### Setup

1. **Install Tailscale** on your server and phone:
   ```bash
   # Linux server
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up

   # iOS/Android — install the Tailscale app from your app store
   ```

2. **Find your Tailscale IP:**
   ```bash
   tailscale ip -4
   # e.g., 100.64.0.1
   ```

3. **Start the Hub:**
   ```bash
   python3 start.py
   # Backend on 0.0.0.0:9099, Frontend on 0.0.0.0:9100
   ```

4. **Access from your phone:**
   ```
   http://100.x.x.x:9100
   ```
   Use the Tailscale IP — this works from anywhere because Tailscale creates a secure WireGuard tunnel.

### Security Notes

- The CORS policy allows `*` (any origin) which is fine on Tailscale since the entire tailnet is authenticated and encrypted
- The backend binds to `0.0.0.0` so it's accessible on both localhost and Tailscale interfaces
- **Do NOT expose ports 9099/9100 to the public internet** — use Tailscale, not port forwarding

### Optional: Tailscale Serve

For a cleaner URL and automatic HTTPS:

```bash
# Serve the frontend over HTTPS with Tailscale's built-in cert
tailscale serve https / http://127.0.0.1:9100

# Now access at: https://your-machine.tail-xxxxx.ts.net
```

This gives you a proper `https://` URL that works from any browser.

### Optional: Run as a Systemd Service

Create `/etc/systemd/system/hermes-hub.service`:

```ini
[Unit]
Description=Hermes Hub Chat Backend and Frontend
After=network.target tailscaled.service

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/smf-hermes-chat-hub
ExecStart=/usr/bin/python3 /home/YOUR_USER/smf-hermes-chat-hub/start.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-hub
sudo systemctl start hermes-hub
```

## How Session Continuity Works

1. **First message**: Backend runs `hermes --profile liam chat -q "Hello"`. The CLI outputs a session ID hint: `hermes --resume abc123`
2. **Session stored**: Backend extracts `abc123` and saves it to the in-memory dict + disk file
3. **Next message**: Backend runs `hermes --profile liam --resume abc123 chat -q "Follow-up"`. The agent has full context from the previous conversation
4. **Backend restart**: On startup, sessions are loaded from `~/.hermes-hub-sessions.json`. The agent picks up where you left off
5. **"New Chat" button**: Sends `DELETE /{profile}` to clear the session ID, starting a fresh conversation

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "hermes binary not found on PATH" | Backend can't find `hermes` | Ensure `which hermes` works in the same shell that runs `backend.py` |
| "Connection error" in browser | Backend isn't running | Run `python3 backend.py` |
| Red status dot on page load | `hermes --version` failed | Check that Hermes Agent is installed (`pip install hermes-agent`) |
| Empty responses | TUI output parsing failure | Check backend logs (uncomment the `log_message` line in `ChatHandler`) |
| Session lost after restart | Sessions file deleted | Backend recreates `~/.hermes-hub-sessions.json` automatically |
| 429 "request already in progress" | Double-clicked send or slow response | Wait for the current request, or cancel it with the Cancel button |

## File Structure

```
smf-hermes-chat-hub/
├── backend.py          # Python HTTP backend — API server, Hermes subprocess management
├── index.html          # SPA frontend — chat UI, agent cards, session management
├── start.py            # Convenience script — starts both backend and frontend servers
├── SKILL.md            # Hermes agent setup skill — point your agent here for auto-configuration
├── TAILSCALE.md        # Detailed Tailscale remote access guide
├── LICENSE             # MIT License
└── README.md           # This file
```

## License

MIT License. See [LICENSE](LICENSE) for details.