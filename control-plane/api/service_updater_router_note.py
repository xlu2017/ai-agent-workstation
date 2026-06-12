"""
Router mounting note for session graph overview.

The session graph overview endpoint is implemented as an independent router in
api.session_graph_overview so it can be included by tests and by the control
plane startup path. When the large server module is next edited directly, include
this router beside api.session_graph.router:

    from api.session_graph_overview import router as session_graph_overview_router
    app.include_router(session_graph_overview_router)

This note exists because the endpoint file and end-to-end API tests are already
present, while the current server module is intentionally large and should be
edited only in focused passes.
"""
