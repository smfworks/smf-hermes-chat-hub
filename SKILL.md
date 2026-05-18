---
name: hermes-hub-setup
description: Set up Hermes Hub — a web chat interface for Hermes Agent profiles. Clones the repo, detects profiles, configures the UI, and starts the servers. Supports Tailscale remote access configuration.
version: 1.0.0
author: SMF Works
license: MIT
metadata:
  hermes:
    tags: [hermes-hub, web-ui, setup, tailscale, chat]
    related_skills: []
---

# Hermes Hub Setup

Deploy and customize a web chat interface for your Hermes Agent profiles.

## Prerequisites

- Python 3.10+
- Hermes Agent installed (`hermes` on PATH)
- Git

## Setup Steps

### 1. Clone the Repository

```bash
git clone https://github.com/smfworks/smf-hermes-chat-hub.git
cd smf-hermes-chat-hub
```

If the repo doesn't exist yet (fresh org setup), ask the user to create it on GitHub first, then clone.

### 2. Detect Available Hermes Profiles

Run `hermes profile list` or check `~/.hermes/profiles/` to find available profiles:

```bash
hermes profile list
```

If `hermes profile list` isn't available, inspect profiles manually:

```bash
ls ~/.hermes/profiles/*/config.yaml 2>/dev/null
# Each directory under ~/.hermes/profiles/ is a profile name
```

Also check which profile is the default:

```bash
cat ~/.hermes/config.yaml | grep default_profile
# or
hermes config get default_profile
```

### 3. Configure Profiles in backend.py

Edit the `PROFILES` dictionary in `backend.py`. Each key is a short ID used in the URL and UI, and the value is the `hermes` CLI command with the appropriate flags:

```python
PROFILES = {
    "default": ["hermes"],
    "your-profile-name": ["hermes", "--profile", "your-profile-name"],
}
```

**Important:** The `"default"` entry should always be present — it uses the default Hermes profile without `--profile`.

Example for a multi-agent setup:
```python
PROFILES = {
    "default": ["hermes"],
    "analyst": ["hermes", "--profile", "analyst"],
    "coder": ["hermes", "--profile", "coder"],
    "reviewer": ["hermes", "--profile", "reviewer"],
}
```

### 4. Configure Agent Cards in index.html

Edit the `agents` array in the `<script>` section of `index.html`. Each agent needs:

```javascript
{
  id: "must-match-PROFILES-key",
  name: "Display Name",
  emoji: "Single character for avatar",
  model: "Model name shown in UI",
  color: "c1 through c6 (maps to CSS color scheme)",
  badge: "Label text, or 'default' for primary, or '' for none"
}
```

Available color schemes:
- `c1`: Green (#7ee787) — recommended for default
- `c2`: Purple (#d2a8ff)
- `c3`: Blue (#79c0ff)
- `c4`: Orange (#ffa657)
- `c5`: Pink (#f778ba)
- `c6`: Light blue (#a5d6ff)

Complete example:
```javascript
const agents = [
  { id: "default", name: "Agent", emoji: "A", model: "deepseek-v4-pro", color: "c1", badge: "default" },
  { id: "analyst", name: "Analyst", emoji: "📊", model: "kimi-k2.6:cloud", color: "c2", badge: "" },
  { id: "coder", name: "Coder", emoji: "💻", model: "deepseek-v4-pro:cloud", color: "c3", badge: "" },
];
```

### 5. Set the API Host (Tailscale)

In `index.html`, the `API_HOST` is set to `window.location.hostname`, which automatically uses whichever hostname or IP you're accessing the page from. This means:

- On localhost: API calls go to `http://localhost:9099`
- On Tailscale: API calls go to `http://100.x.x.x:9099`

**No additional configuration is needed** — it just works. If you need to override it, change the `API` constant:

```javascript
const API = 'http://YOUR_SERVER_IP:9099';
```

### 6. Start the Hub

```bash
# Start both backend and frontend
python3 start.py

# Or start them separately:
python3 backend.py           # API server on port 9099
python3 -m http.server 9100  # Frontend on port 9100
```

Access at: `http://localhost:9100`

### 7. (Optional) Configure Tailscale Remote Access

If the user wants phone/remote access:

1. Install Tailscale on the server and phone
2. Run `tailscale ip -4` to get the server's Tailscale IP
3. Access from phone at `http://100.x.x.x:9100`

For HTTPS with automatic certificates:
```bash
tailscale serve https / http://127.0.0.1:9100
# Access at: https://myserver.tail-XXXXX.ts.net
```

See `TAILSCALE.md` for the complete guide.

### 8. (Optional) Run as a Systemd Service

```bash
# Create service file
sudo tee /etc/systemd/system/hermes-hub.service << 'EOF'
[Unit]
Description=Hermes Hub Chat Backend and Frontend
After=network.target tailscaled.service

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/smf-hermes-chat-hub
ExecStart=/usr/bin/python3 /home/YOUR_USERNAME/smf-hermes-chat-hub/start.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now hermes-hub
```

## Verification

After setup, verify everything works:

1. **Backend health:** Visit `http://localhost:9099/health` — should return `{"status": "ok", "hermes": true}`
2. **Frontend:** Visit `http://localhost:9100` — should show agent cards
3. **Chat:** Click an agent, type a message, verify response comes back
4. **Sessions:** Send a second message, verify context is maintained (session_id appears in health check)
5. **Error recovery:** Stop the backend, send a message (should see error with retry button), restart backend (health dot turns green), retry

## Customization Tips

- **Change the port:** Edit `PORT` in `backend.py` and `FRONTEND_PORT` in `start.py`
- **Change the title:** Edit `<title>` and the `<h1>` in `index.html`
- **Change colors:** Edit CSS variables in `:root` at the top of `<style>` in `index.html`
- **Add/remove agents:** Edit both `PROFILES` in `backend.py` AND `agents` in `index.html` — they must match
- **Adjust timeouts:** Edit `TIMEOUT`, `MAX_RETRIES`, and `RETRY_DELAY` in `backend.py`
- **Session storage:** Sessions persist to `~/.hermes-hub-sessions.json` — delete this file to clear all sessions

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `hermes binary not found on PATH` | Ensure `which hermes` works in the same shell context |
| Frontend loads but chat gives "Connection error" | Backend isn't running on port 9099 |
| Chat works but responses are garbled | TUI output parsing issue — check backend logs |
| Session context lost between messages | Check `~/.hermes-hub-sessions.json` is writable |
| 429 "request already in progress" | Previous request still running — use Cancel or wait |