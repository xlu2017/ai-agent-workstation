# Remote Desktop Access Guide

This guide covers all methods to interact with your AI workstation's desktop and terminal.

## Server Details

| Field | Value |
|-------|-------|
| Hostname | `workstation` |
| Public IP | `<server-ip>` |
| SSH User | `agent` |
| Desktop | XFCE 4 via xRDP |
| RDP Port | 3389 |

---

## Method 1: SSH (Primary — Terminal Only)

The fastest and most reliable way to interact with the server.

### Connect

```bash
ssh -i ~/.ssh/hetzner_workstation agent@<server-ip>
```

### First-time setup (add key to local SSH config)

Add to `~/.ssh/config`:

```
Host workstation
    HostName <server-ip>
    User agent
    IdentityFile ~/.ssh/hetzner_workstation
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

Then connect with just:

```bash
ssh workstation
```

### Port forwarding (access web UIs locally)

Forward OpenHands and LiteLLM to your local machine:

```bash
ssh -L 3000:localhost:3000 -L 4000:localhost:4000 workstation
```

Then open in your local browser:
- OpenHands: http://localhost:3000
- LiteLLM Admin: http://localhost:4000/ui

---

## Method 2: RDP (Graphical Desktop)

Full XFCE desktop accessible via any RDP client. Useful for:
- Running browsers on the server
- Visual debugging
- GUI applications

### RDP Client Recommendations

| Platform | Client | Install |
|----------|--------|---------|
| **macOS** | Microsoft Remote Desktop | [App Store](https://apps.apple.com/app/microsoft-remote-desktop/id1295203466) |
| **Windows** | Built-in Remote Desktop | `mstsc.exe` (pre-installed) |
| **Linux** | Remmina | `sudo apt install remmina remmina-plugin-rdp` |
| **Linux (CLI)** | FreeRDP | `sudo apt install freerdp2-x11` |

### Connection Settings

| Setting | Value |
|---------|-------|
| Host/Server | `<server-ip>` |
| Port | `3389` |
| Username | `agent` |
| Password | *(set during setup — see below)* |
| Color Depth | 24-bit or 32-bit |
| Resolution | 1920x1080 (or your preference) |

### Set/Change RDP Password

The `agent` user needs a password for xRDP login (SSH keys don't work for RDP):

```bash
ssh workstation
sudo passwd agent
# Enter new password when prompted
```

### Connect via CLI (Linux)

```bash
xfreerdp /v:<server-ip> /u:agent /size:1920x1080 /cert:ignore
```

You'll be prompted for the password.

### Troubleshooting RDP

| Issue | Solution |
|-------|----------|
| Black screen after login | Wait 5-10 seconds; XFCE may be slow to start |
| "Login failed" | Verify password with `ssh workstation` then `sudo passwd agent` |
| Connection refused | Check firewall: `sudo ufw status` — port 3389 must be open |
| Slow/laggy | Reduce color depth to 16-bit; use wired connection |
| Clipboard not working | Restart xrdp: `sudo systemctl restart xrdp` |

---

## Method 3: Tailscale (Recommended for Production)

Tailscale provides encrypted mesh networking without exposing ports to the public internet.

### Setup (one-time)

```bash
ssh workstation
sudo tailscale up
```

Follow the URL to authenticate in your Tailscale account.

### After Tailscale is active

Your server gets a Tailscale hostname (e.g., `workstation`) and IP (e.g., `100.x.y.z`).

Access via Tailscale:
```bash
ssh agent@workstation   # Tailscale hostname
ssh agent@100.x.y.z            # Tailscale IP
```

RDP via Tailscale (more secure — no public port needed):
```
Host: 100.x.y.z (or Tailscale hostname)
Port: 3389
```

### Lock down after Tailscale

Once Tailscale is working, remove public RDP access:

```bash
ssh workstation
sudo ufw delete allow 3389/tcp
```

RDP will only be accessible through Tailscale after this.

---

## Method 4: VS Code Remote SSH

For code editing with full IDE features:

1. Install [Remote - SSH extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh)
2. Press `Ctrl+Shift+P` → "Remote-SSH: Connect to Host"
3. Enter `agent@<server-ip>` (or use your SSH config alias `workstation`)
4. VS Code opens a remote session with full editor, terminal, and extensions

---

## Security Best Practices

### Current firewall rules

```
SSH (22/tcp)     — open to all (key-only auth)
RDP (3389/tcp)  — open to all (password auth) ← close after Tailscale setup
```

### Recommended hardening steps

1. **Set up Tailscale** → access everything through encrypted tunnel
2. **Close port 3389** from public → `sudo ufw delete allow 3389/tcp`
3. **Use SSH port forwarding** for web UIs instead of exposing ports
4. **Change SSH port** (optional): edit `/etc/ssh/sshd_config`, update UFW rules

### Fail2ban

Already configured — blocks IPs after 5 failed SSH attempts for 1 hour.

Check status:
```bash
sudo fail2ban-client status sshd
```

---

## Quick Reference

```bash
# SSH into server
ssh workstation

# Forward web UIs to localhost
ssh -L 3000:localhost:3000 -L 4000:localhost:4000 workstation

# RDP from Linux CLI
xfreerdp /v:<server-ip> /u:agent /size:1920x1080 /cert:ignore

# Check running services
ssh workstation 'docker ps'

# View service logs
ssh workstation 'cd ~/ai-workstation && docker compose logs -f'

# Start tmux sessions
ssh workstation '~/ai-workstation/scripts/start-sessions.sh'

# Attach to dev session
ssh workstation -t 'tmux attach -t ws-dev'
```
