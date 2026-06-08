# Browser Remote Desktop Operations

Apache Guacamole is the supported browser remote desktop path. It avoids a custom RDP client in the dashboard: the browser uses Guacamole's HTML5 client, while `guacd` handles the RDP connection to xRDP over the private Tailscale/server network.

## Target flow

```text
Windows browser
  -> /remote-desktop
  -> /guacamole/
  -> guacamole webapp
  -> guacd
  -> xRDP on dev-server:3389
  -> XFCE desktop
```

## Start

```bash
cd ~/jubilant-goggles
cp ops/remote-desktop/.env.example ops/remote-desktop/.env
nano ops/remote-desktop/.env
docker compose --env-file ops/remote-desktop/.env -f ops/remote-desktop/docker-compose.guacamole.yml up -d
```

Set `RDP_PASSWORD` and replace `POSTGRES_PASSWORD` in the local `.env` file. Do not commit this file.

## Connect

Direct development URL:

```text
http://<tailscale-ip>:8080/guacamole/
```

Preferred dashboard URL with same-origin proxy:

```text
http://<tailscale-ip>:5173/remote-desktop
```

Production should use a private host/domain:

```text
https://<private-host>/remote-desktop
https://<private-host>/guacamole/
```

## Verify

```bash
curl -I http://127.0.0.1:8080/guacamole/
curl http://127.0.0.1:<CONTROL_PLANE_PORT>/api/v2/remote-desktop/health
```

From Windows on the tailnet:

```powershell
Test-NetConnection <tailscale-ip> -Port 8080
```

From outside the tailnet, public RDP should fail:

```bash
nc -vz <public-ip> 3389
```

## Reverse proxy

Use same-origin proxying when embedding Guacamole in the dashboard. It avoids iframe, CORS, cookie, and WebSocket friction.

Nginx:

```nginx
location /guacamole/ {
    proxy_pass http://127.0.0.1:8080/guacamole/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
}
```

Caddy:

```caddyfile
handle_path /guacamole/* {
    reverse_proxy 127.0.0.1:8080 {
        header_up Host {host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

## Performance settings

Use the seeded connection defaults first:

- `color-depth=16`; increase to `24` on strong links.
- Wallpaper off.
- Font smoothing off if latency matters.
- Desktop composition off.
- `resize-method=display-update`.
- Audio off.
- Drive redirection off.

## Security settings

- Keep Guacamole Tailscale-only or behind authenticated dashboard proxying.
- Keep `guacd` on the Docker network only.
- Keep xRDP private; public TCP `3389` must remain blocked.
- Do not commit `.env` or RDP credentials.
- Prefer SSO/dashboard auth in front of Guacamole for production.

## Compared with Windows `mstsc`

`mstsc` is a native desktop RDP client that connects directly to port `3389`. Guacamole keeps that RDP connection server-side. The browser receives the rendered session through Guacamole's HTML5/WebSocket client, so users do not install a desktop client.

## Troubleshooting

### Blank screen

- Confirm XFCE starts for the configured user.
- Use `GUACAMOLE_RDP_COLOR_DEPTH=16`.
- Disable XFCE compositor effects.
- Check logs:

  ```bash
  docker compose --env-file ops/remote-desktop/.env -f ops/remote-desktop/docker-compose.guacamole.yml logs guacamole guacd
  ```

### Login failure

- Check `RDP_HOST`, `RDP_PORT`, and `RDP_USERNAME`.
- Re-enter `RDP_PASSWORD` in the local `.env`.
- Test private reachability:

  ```bash
  nc -vz "$RDP_HOST" "$RDP_PORT"
  ```

### Iframe blocked

Use same-origin `/guacamole/` proxying. If a different origin is unavoidable, configure Guacamole/proxy security headers to allow framing only from the dashboard origin.
