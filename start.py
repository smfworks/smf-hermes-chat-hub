#!/usr/bin/env python3
"""
Hermes Hub startup script — launches both the backend API server
and the static frontend server.
"""

import subprocess, sys, os, signal, time

BACKEND_PORT = 9099
FRONTEND_PORT = 9100
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

procs = []

def cleanup(signum=None, frame=None):
    print("\n🛑 Shutting down servers...")
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# Start backend
print(f"🚀 Starting backend on port {BACKEND_PORT}...")
backend = subprocess.Popen(
    [sys.executable, os.path.join(SCRIPT_DIR, 'backend.py')],
    cwd=SCRIPT_DIR,
)
procs.append(backend)

# Give backend a moment to start
time.sleep(1)
if backend.poll() is not None:
    print(f"❌ Backend failed to start (exit code {backend.returncode})")
    sys.exit(1)

# Start frontend
print(f"🌐 Starting frontend on port {FRONTEND_PORT}...")
frontend = subprocess.Popen(
    [sys.executable, '-m', 'http.server', str(FRONTEND_PORT)],
    cwd=SCRIPT_DIR,
)
procs.append(frontend)

print(f"\n✅ Hermes Hub running!")
print(f"   Frontend: http://localhost:{FRONTEND_PORT}")
print(f"   Backend:  http://localhost:{BACKEND_PORT}")
print(f"   Press Ctrl+C to stop\n")

# Wait for either to exit
try:
    while True:
        for i, p in enumerate(procs):
            if p.poll() is not None:
                name = "backend" if i == 0 else "frontend"
                print(f"❌ {name} exited unexpectedly (code {p.returncode})")
                cleanup()
                sys.exit(1)
        time.sleep(1)
except KeyboardInterrupt:
    cleanup()