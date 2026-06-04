---
name: devin-tailscale-workstation
description: Use this skill whenever Devin needs to connect to, administer, deploy, debug, or inspect the AI Coding Agent Workstation server over SSH, Tailscale SSH, RDP, LiteLLM, OpenHands, the Control Plane, Docker, or systemd. Use it especially when the user mentions Devin Desktop, Windows, Linux, Tailscale, ordinary SSH, provider firewall, Hetzner, port 22, xRDP, LiteLLM, or the workstation server.
---

# Devin ↔ Tailscale Workstation Access

This repository's intended access model is Tailscale-only for SSH:

- Do **not** use the server's public IP for SSH.
- Treat successful public-IP SSH as a security defect to report and fix.
- Do **not** open public admin ports from scripts.
- Use Tailscale SSH for tailnet port `22` on Linux servers.
- Block ordinary non-Tailscale SSH at the host by moving OpenSSH to `127.0.0.1:2222`.
- Block ordinary public SSH at the provider/cloud firewall.
- Use SSH port forwarding over Tailscale for private admin UIs.
- Use `sudo` for full server permissions only after verifying the session is on the expected tailnet host.

The workstation no longer relies on `ufw` or `fail2ban` for host-level access control. Provider firewall policy and Tailscale ACLs/grants are the ingress controls.

## Mental model

There are three separate access paths:

| Path | Use | Expected address |
|---|---|---|
| Tailscale SSH | Primary Linux server shell access | `ssh agent@<tailscale-hostname>` or `ssh agent@100.x.y.z` |
| OpenSSH localhost fallback | Recovery from provider console only | `ssh -p 2222 agent@127.0.0.1` |
| SSH forwarding over Tailscale | Private web/admin UIs | `ssh -L local:localhost:remote agent@<tailscale-hostname>` |

Forbidden routine paths:

| Path | Expected result |
|---|---|
| `ssh agent@<server-public-ip>` | must fail |
| `ssh -p 22 agent@<server-public-ip>` | must fail |
| `ssh -p 2222 agent@<server-public-ip>` | must fail |
| OpenSSH listening on `0.0.0.0:22`, `[::]:22`, public IP `:22`, or LAN IP `:22` | configuration defect |

Never infer that a public port is safe just because Tailscale is installed. Public exposure is controlled by the provider firewall, and ordinary OpenSSH must not listen on any non-loopback interface.

## Required operator setup

Before Devin can work reliably, the user/operator must ensure:

1. The server is joined to the tailnet.
2. The Devin Desktop environment that will initiate SSH is also joined to the tailnet, or can otherwise reach a Tailscale-connected client.
3. MagicDNS is enabled, or the server's Tailscale IPv4 address is known.
4. Tailscale policy permits the Devin/user identity to reach the workstation on port `22`.
5. The provider firewall blocks ordinary public admin ingress, especially TCP `22`, `3389`, `4000`, `9877`, `3000`, `3010+`, `9100`, and `9876`, unless a port is intentionally public.
6. The server user used by Devin, normally `agent`, has the intended privilege level. For full administration, `agent` should be able to run `sudo -n` without an interactive password prompt.

If any of these conditions are not true, stop and report the missing prerequisite rather than falling back to the public IP.

## Tailnet policy template

Use placeholders; do not commit real emails, secrets, auth keys, or tailnet names.

```json
{
  "tagOwners": {
    "tag:workstation": ["autogroup:admin"],
    "tag:devin": ["autogroup:admin"]
  },
  "grants": [
    {
      "src": ["tag:devin", "autogroup:admin"],
      "dst": ["tag:workstation"],
      "ip": ["tcp:22", "tcp:3389", "tcp:9877", "tcp:4000", "tcp:3000", "tcp:3010-3099"]
    }
  ],
  "ssh": [
    {
      "action": "accept",
      "src": ["tag:devin", "autogroup:admin"],
      "dst": ["tag:workstation"],
      "users": ["agent"]
    }
  ]
}
```

Notes:

- Prefer `agent` with passwordless sudo over direct root SSH.
- Use Tailscale `check` mode only when human re-authentication is acceptable. Automated Devin workflows often open multiple SSH connections and can fail or hang if check mode is required for every connection.
- For highly sensitive operations, ask the user to approve temporarily elevated policy rather than broadening defaults permanently.

## First connection checklist

From Devin Desktop on Linux:

```bash
tailscale status
tailscale ip -4
ssh agent@<tailscale-hostname> 'hostname; whoami; tailscale ip -4; sudo -n true && echo sudo-ok'
```

From Devin Desktop on Windows PowerShell:

```powershell
tailscale status
tailscale ip -4
ssh agent@<tailscale-hostname> "hostname; whoami; tailscale ip -4; sudo -n true && echo sudo-ok"
```

If `sudo -n true` fails, Devin does not have noninteractive full permissions. Report that clearly and ask the user to grant the intended privilege or provide a different operational path.

## Server-side Tailscale-only SSH configuration

For the current Linux workstation, after Tailscale is authenticated and a tailnet SSH path has been tested, run:

```bash
sudo /opt/workstation/scripts/configure-tailscale-ssh-only.sh
```

Expected result:

- Tailscale SSH handles tailnet port `22`.
- Ordinary OpenSSH listens only on `127.0.0.1:2222`.
- OpenSSH does not listen on public, LAN, wildcard, or Tailscale network addresses.
- Public TCP `22` is blocked by the provider firewall.

Verify:

```bash
ssh agent@<tailscale-hostname> 'hostname; whoami; sudo -n true && echo sudo-ok'
ssh agent@<tailscale-hostname> 'sudo -n ss -tlnp | grep sshd || true'
ssh agent@<server-public-ip> 'echo should-not-connect'
ssh -p 2222 agent@<server-public-ip> 'echo should-not-connect'
```

The public-IP commands must fail. The only expected `sshd` listener is `127.0.0.1:2222` or `[::1]:2222`; Tailscale SSH is handled by `tailscaled`, not network-facing OpenSSH.

## Routine server operations

Always connect by Tailscale hostname/IP:

```bash
ssh agent@<tailscale-hostname>
```

Use explicit noninteractive sudo checks before privileged changes:

```bash
ssh agent@<tailscale-hostname> 'sudo -n true'
```

Use SSH forwarding for private admin UIs:

```bash
ssh -N \
  -L 9877:localhost:9877 \
  -L 4000:localhost:4000 \
  -L 3000:localhost:3000 \
  agent@<tailscale-hostname>
```

Then access locally from the Devin Desktop browser:

- Control Plane: `http://localhost:9877`
- LiteLLM: `http://localhost:4000/ui`
- OpenHands: `http://localhost:3000` or the allocated local forwarded port

For one-shot commands:

```bash
ssh agent@<tailscale-hostname> 'cd /opt/workstation && git status && docker ps'
```

For deployment or service repair:

```bash
ssh agent@<tailscale-hostname> 'sudo -n systemctl status tailscaled --no-pager'
ssh agent@<tailscale-hostname> 'sudo -n systemctl status docker --no-pager'
ssh agent@<tailscale-hostname> 'cd /home/agent/ai-workstation && docker compose ps'
```

## Provider firewall expectations

Provider firewall is the public edge gate. It should deny inbound public admin traffic:

```text
Public inbound deny by default:
  tcp/22      ordinary public SSH
  tcp/2222    OpenSSH localhost fallback must not be public
  tcp/3389    RDP
  tcp/4000    LiteLLM
  tcp/9877    Control Plane
  tcp/3000    OpenHands default
  tcp/3010+   allocated OpenHands/dev ports
  tcp/9100    Node Exporter
  tcp/9876    UI Bridge
```

Allow public `80/443` only for intentional public web serving. Keep a documented break-glass method such as provider console access or a temporary provider firewall rule.

## Windows and Linux Devin Desktop guidance

Use the same logical target from both desktop environments:

```text
agent@<tailscale-hostname>
```

Do not create separate public-IP host entries for Windows and Linux. If SSH config is needed, use this shape on both platforms, adapting the path location:

```sshconfig
Host ai-workstation
  HostName <tailscale-hostname>
  User agent
  Port 22
  ServerAliveInterval 30
  ServerAliveCountMax 3
  ForwardAgent no
```

Linux SSH config path:

```text
~/.ssh/config
```

Windows OpenSSH config path:

```text
%USERPROFILE%\.ssh\config
```

## Future Windows PC server guidance

Tailscale SSH server support is not equivalent across all platforms. For a future Windows PC acting as the server, use ordinary Windows OpenSSH over the Tailscale IP/name unless Tailscale SSH server support for that platform is explicitly available and tested.

Target Windows-server model:

1. Install Tailscale on the Windows PC and join the same tailnet.
2. Enable OpenSSH Server on Windows.
3. Bind/allow SSH for tailnet access and block public SSH at the router/provider/firewall.
4. Use Tailscale ACLs/grants to restrict which Devin/admin identities can reach `tcp:22`.
5. Use a Windows administrator account only when required; otherwise use a dedicated automation account with the minimum needed rights.

Preferred connection:

```powershell
ssh <windows-admin-or-automation-user>@<windows-pc-tailscale-hostname>
```

Do not assume the Linux helper script `configure-tailscale-ssh-only.sh` applies to Windows.

## Troubleshooting

Check tailnet reachability:

```bash
tailscale status
tailscale ping <tailscale-hostname>
```

Check server listening ports:

```bash
ssh agent@<tailscale-hostname> 'sudo -n ss -tlnp | grep -E ":22|:2222|:3389|:4000|:9877|:3000|:3010" || true'
```

Check Tailscale SSH status:

```bash
ssh agent@<tailscale-hostname> 'sudo -n tailscale status; sudo -n tailscale ip -4'
```

If tailnet SSH fails but provider console works, recover OpenSSH locally on the server:

```bash
ssh -p 2222 agent@127.0.0.1
ls -1 /etc/ssh/sshd_config.pre-tailscale-ssh-only.*
sudo cp /etc/ssh/sshd_config.pre-tailscale-ssh-only.<timestamp> /etc/ssh/sshd_config
sudo systemctl restart ssh || sudo systemctl restart sshd
```

## Safety rules for Devin

- Never ask the user to paste private keys, Tailscale auth keys, API keys, or passwords into the repo.
- Never commit real tailnet policy containing private emails unless the user explicitly asks and the repository is private.
- Never switch to public IP SSH merely because Tailscale fails; diagnose Tailscale/provider policy first.
- Treat any successful SSH to the server public IP as a misconfiguration to report and fix.
- Never open public admin ports from scripts.
- Before destructive operations, record the hostname, current user, git branch, service name, and rollback command.
- Prefer idempotent commands and `sudo -n` to avoid hanging on password prompts.
