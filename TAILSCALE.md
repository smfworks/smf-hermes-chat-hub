# Tailscale Remote Access Guide

Access your Hermes Hub from your phone, tablet, or any device — securely, without port forwarding.

## Why Tailscale?

Hermes Hub runs on your server. You want to access it from your phone on the go. Options:

| Method | Security | Setup | Works Anywhere |
|--------|----------|-------|----------------|
| Port forwarding | ❌ Exposed to internet | Medium | Yes |
| SSH tunnel | ✅ Encrypted | Annoying on mobile | Limited |
| Cloudflare Tunnel | ✅ Encrypted | Complex | Yes |
| **Tailscale** | ✅ WireGuard encrypted | **2 minutes** | **Yes** |

Tailscale is the clear winner for this use case. Your Hub is only accessible to authenticated devices on your tailnet, all traffic is encrypted, and setup is trivial.

## Quick Setup (5 minutes)

### Step 1: Install Tailscale

**On your server (Linux):**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

**On your phone:**
- iOS: App Store → "Tailscale"
- Android: Play Store → "Tailscale"
- Log in with the same account

### Step 2: Find Your Server's Tailscale IP

```bash
tailscale ip -4
# Output: 100.64.0.1  (your IP will be different)
```

### Step 3: Start Hermes Hub

```bash
cd ~/smf-hermes-chat-hub
python3 start.py
```

The backend binds to `0.0.0.0:9099` and the frontend to `0.0.0.0:9100` — both are accessible on the Tailscale IP.

### Step 4: Open on Your Phone

```
http://100.x.x.x:9100
```

That's it. The page loads, you see your agent cards, and you can chat from anywhere.

## Enhanced Setup: HTTPS with Tailscale Serve

Plain HTTP works fine on Tailscale since the WireGuard tunnel is encrypted, but if you want a proper HTTPS URL (some browsers complain about HTTP):

```bash
# Enable Tailscale Serve — proxies HTTPS to your frontend
tailscale serve https / http://127.0.0.1:9100

# You'll get a URL like:
# https://myserver.tail12345.ts.net
```

Now access from any device:
- `https://myserver.tail12345.ts.net` — clean HTTPS URL
- Works in any browser without warnings
- Certificate is automatically managed by Tailscale

To remove:
```bash
tailscale serve reset
```

## Running as a Background Service

### Systemd (recommended for Linux servers)

Create `/etc/systemd/system/hermes-hub.service`:

```ini
[Unit]
Description=Hermes Hub Chat Backend and Frontend
After=network.target tailscaled.service
Wants=tailscaled.service

[Service]
Type=simple
User=YOUR_LINUX_USERNAME
WorkingDirectory=/home/YOUR_LINUX_USERNAME/smf-hermes-chat-hub
ExecStart=/usr/bin/python3 /home/YOUR_LINUX_USERNAME/smf-hermes-chat-hub/start.py
Restart=on-failure
RestartSec=5
Environment=HOME=/home/YOUR_LINUX_USERNAME
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-hub
sudo systemctl start hermes-hub

# Check status
sudo systemctl status hermes-hub

# View logs
sudo journalctl -u hermes-hub -f
```

### tmux (quick and dirty)

```bash
tmux new -s hermes-hub
cd ~/smf-hermes-chat-hub
python3 start.py
# Ctrl+B, D to detach
# tmux attach -t hermes-hub to reattach
```

## Firewall Notes

If you're using a firewall (ufw, iptables, etc.), Tailscale traffic goes through the `tailscale0` interface. You typically don't need to open ports in your firewall — Tailscale handles its own routing.

However, if you also want local network access:

```bash
# Allow local access (optional)
sudo ufw allow from 192.168.0.0/16 to any port 9100
sudo ufw allow from 192.168.0.0/16 to any port 9099

# Tailscale traffic is on 100.64.0.0/10 — already handled by Tailscale
```

## Security Checklist

- [x] Backend CORS allows `*` — safe because Tailscale authenticates at the network level
- [x] No API keys needed — the Hub is only accessible on your tailnet
- [ ] **Do NOT expose ports 9099/9100 to the public internet** — no port forwarding, no public IP binding
- [x] Request body size limits prevent abuse (64KB max)
- [x] Message length limits prevent abuse (32K chars max)
- [x] Concurrent request protection (429 on double-submit)

## Troubleshooting Tailscale Access

| Problem | Check |
|---------|-------|
| Can't reach the page | `tailscale status` — is the server connected? Is your phone on the same tailnet? |
| Page loads but chat fails | Backend isn't running — `curl http://100.x.x.x:9099/health` |
| Connection timeout | Firewall blocking Tailscale traffic — check `ufw status` |
| "Backend offline" in UI | Backend process died — check `systemctl status hermes-hub` |
| Works on WiFi but not cellular | Tailscale might be in "exit node" mode — check Tailscale app settings