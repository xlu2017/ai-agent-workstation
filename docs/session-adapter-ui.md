# Session adapter UI scaffold

The dashboard includes a placeholder Session Graph page at `/session-graph`.
The current scaffold uses the existing React/Vite stack and plain CSS. React
Flow is the intended graph renderer once interactive node layout is added.

It includes:

- session graph explorer
- mounted sources section
- adapter detail panel
- context projection summary
- future React Flow node/edge canvas
- buttons for "View original session" and "View adapted projection"

The UI is intentionally minimal. It provides a coherent place to inspect graph
state while the execution loop and persistence layer are integrated later.

## Data source

The page loads `GET /api/session-graph/snapshot`.

## Later integration points

- Link session rows to the existing session detail page.
- Render adapter mappings with confirmation controls.
- Add a preview form for mount requests.
- Add active-session switching once policy and locking are wired in.
- Replace the list-style explorer with React Flow nodes, edges, sub-flows, and
  nested container rendering.
