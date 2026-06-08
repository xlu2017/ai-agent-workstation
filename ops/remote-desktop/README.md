# Browser Remote Desktop with Apache Guacamole

This stack provides browser-based access to the workstation desktop without exposing RDP to the public internet. The browser loads the Guacamole web client, Guacamole talks to `guacd`, and `guacd` connects to xRDP on the private Tailscale/server path.

```text
Browser dashboard
  -> /remote-desktop
  -> /guacamole/ same-origin proxy or localhost Guacamole webapp
  -> guacd container
  -> xRDP on RDP_HOST:RDP_PORT
  -> XFCE desktop
```

## Files

```text
ops/remote-desktop/
├── docker-compose.guacamole.yml
├── .env.example
└── README.md
```

## Start Guacamole

```bash
cd ~/jubilant-goggles
cp ops/remote-desktop/.env.example ops/remote-desktop/.env
nano ops/remote-desktop/.env
docker compose --env-file ops/remote-desktop/.env -f ops/remote-desktop/docker-compose.guacamole.yml up -d
```

Set `RDP_PASSWORD` only in the local `.env` file. Do not commit it.

The compose stack initializes Guacamole's Postgres schema and creates a default `Workstation xRDP` connection from the `RDP_*` values. The default Guacamole admin login is created by Guacamole's schema; change it immediately after first login.

## Local verification

```bash
curl -I http://127.0.0.1:8080/guacamole/
curl http://127.0.0.1:<CONTROL_PLANE_PORT>/api/v2/remote-desktop/config
curl http://127.0.0.1:<CONTROL_PLANE_PORT>/api/v2/remote-desktop/health
```

From a Windows machine on the tailnet:

```powershell
Test-NetConnection 100.119.21.55 -Port 8080
```

Open one of:

```text
http://100.119.21.55:8080/guacamole/
http://100.119.21.55:5173/remote-desktop
```

Prefer the dashboard route once the same-origin proxy is configured.

## Dashboard integration

The dashboard page at `/remote-desktop` reads:

```text
GET /api/v2/remote-desktop/config
GET /api/v2/remote-desktop/health
```

It never displays usernames, passwords, tokens, or connection secrets. The page embeds `GUACAMOLE_URL`, which defaults to `/guacamole/`.

## Reverse proxy

Same-origin routing avoids most iframe, CORS, cookie, and WebSocket issues:

```text
https://<private-host>/remote-desktop
https://<private-host>/guacamole/
```

### Nginx

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

### Caddy

```caddyfile
handle_path /guacamole/* {
    reverse_proxy 127.0.0.1:8080 {
        header_up Host {host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

For Vite development, `control-plane/web/vite.config.ts` proxies `/guacamole` to `http://127.0.0.1:8080`.

## Performance defaults

The generated Guacamole connection uses settings that favor latency:

- Color depth: `GUACAMOLE_RDP_COLOR_DEPTH=16` by default; use `24` on better links.
- Wallpaper: disabled.
- Font smoothing: disabled.
- Desktop composition: disabled.
- Menu animations: disabled.
- Resize method: `display-update`.
- Audio: disabled.
- Drive redirection: disabled.

Enable audio or drive redirection only when needed.

## Security boundary

- Guacamole must be reachable only through Tailscale or an authenticated dashboard proxy.
- `guacd` is only exposed on the Docker network.
- xRDP must remain bound to the Tailscale/private path or protected by provider firewall and Tailscale ACLs.
- Public TCP `3389` must remain blocked.
- Do not commit `.env`, RDP credentials, database passwords, or real tailnet policy.
- Prefer dashboard SSO/auth in front of Guacamole for longer-term production use.

## Verify public RDP is blocked

From a non-tailnet network:

```bash
nc -vz <public-ip> 3389
```

The connection should fail. From a tailnet client, the private target should be reachable only if policy allows it:

```bash
nc -vz 100.119.21.55 3389
```

## How this differs from `mstsc`

Windows `mstsc` connects directly to RDP from the desktop client. Guacamole keeps the RDP connection server-side: the browser speaks HTML5/WebSocket to Guacamole, then `guacd` speaks RDP to xRDP over the private path. Users do not need to install a desktop RDP client.

## Troubleshooting

### Blank screen

- Confirm XFCE starts for the `RDP_USERNAME`.
- Lower `GUACAMOLE_RDP_COLOR_DEPTH` to `16`.
- Disable compositor effects in XFCE.
- Check Guacamole logs:

  ```bash
  docker compose --env-file ops/remote-desktop/.env -f ops/remote-desktop/docker-compose.guacamole.yml logs guacamole guacd
  ```

### Login failure

- Confirm `RDP_HOST`, `RDP_PORT`, `RDP_USERNAME`, and the local `RDP_PASSWORD`.
- Test RDP reachability from the server:

  ```bash
  nc -vz "$RDP_HOST" "$RDP_PORT"
  ```

- Recreate the Guacamole database volume if the seeded connection was created with the wrong values:

  ```bash
  docker compose --env-file ops/remote-desktop/.env -f ops/remote-desktop/docker-compose.guacamole.yml down
  docker volume rm workstation-remote-desktop_guacamole-postgres-data workstation-remote-desktop_guacamole-init
  docker compose --env-file ops/remote-desktop/.env -f ops/remote-desktop/docker-compose.guacamole.yml up -d
  ```
