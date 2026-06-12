"""Session graph API services."""


def _wire_budgeted_context_projection() -> None:
    """Use the dynamic projection-budget implementation in the SessionAdapter Engine.

    The engine looks up ``generate_context_projection`` at runtime when mount and adapt
    operations execute, so replacing the module attribute here wires the existing call
    path without changing the rest of the engine scaffold.
    """
    from api.services import context_projection_service, session_adapter_engine

    session_adapter_engine.generate_context_projection = context_projection_service.generate_budgeted_context_projection


_wire_budgeted_context_projection()
