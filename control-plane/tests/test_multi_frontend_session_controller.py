from __future__ import annotations

from api.models.multi_frontend import BackendInstance, CreateMultiFrontendTopologyRequest, DeviceProfile, FrontendInstance, FrontendRuntimeKind, InstanceHealth, OperatingSystemFamily, RegisterCrossClientTraceRequest, StateIsolationMode
from api.models.session_graph import EdgeType, SessionKind
from api.services.multi_frontend_session_controller import MultiFrontendSessionController
from api.services.session_graph_service import SessionGraphStore


def _request() -> CreateMultiFrontendTopologyRequest:
    backend = BackendInstance(label="API", base_url="http://127.0.0.1:8080", health=InstanceHealth.HEALTHY, port=8080)
    web = FrontendInstance(
        label="Chrome desktop",
        device_profile=DeviceProfile(label="Chrome desktop", os_family=OperatingSystemFamily.WEB, runtime_kind=FrontendRuntimeKind.BROWSER, viewport_width=1440, viewport_height=900, browser_name="chrome"),
        backend_instance_id=backend.id,
        target_base_url=backend.base_url,
        current_url="http://127.0.0.1:8080/checkout",
        auth_identity="web-user@example.test",
    )
    android = FrontendInstance(
        label="Android emulator",
        device_profile=DeviceProfile(label="Pixel emulator", os_family=OperatingSystemFamily.ANDROID, runtime_kind=FrontendRuntimeKind.EMULATOR, viewport_width=412, viewport_height=915, emulator_name="pixel-8"),
        backend_instance_id=backend.id,
        target_base_url=backend.base_url,
        current_url="http://10.0.2.2:8080/checkout",
        auth_identity="android-user@example.test",
    )
    return CreateMultiFrontendTopologyRequest(app_title="Checkout App", intent="Compare web and Android checkout against one backend.", backend=backend, frontends=[web, android], isolation_mode=StateIsolationMode.SHARED_BACKEND_SEPARATE_USER)


def test_create_topology_writes_session_graph(tmp_path):
    store = SessionGraphStore(tmp_path / "graph.json")
    controller = MultiFrontendSessionController(store)
    topology = controller.create_topology(_request())
    graph = store.load()

    assert topology.backend.session_id is not None
    assert len(topology.frontends) == 2
    assert len(graph.sessions) == 4
    assert any(session.kind == SessionKind.APP for session in graph.sessions)
    assert sum(1 for edge in graph.edges if edge.type == EdgeType.CONTAINS) == 3
    assert sum(1 for edge in graph.edges if edge.type == EdgeType.DEPENDS_ON) == 2


def test_trace_headers_identify_frontend_and_backend(tmp_path):
    store = SessionGraphStore(tmp_path / "graph.json")
    controller = MultiFrontendSessionController(store)
    topology = controller.create_topology(_request())
    frontend = topology.frontends[0]
    headers = controller.build_trace_headers(root_session_id=topology.root_session_id, frontend_instance_id=frontend.id, user_flow_id="checkout-flow", trace_id="trace-123")

    assert headers.root_session_id == topology.root_session_id
    assert headers.backend_session_id == topology.backend.session_id
    assert headers.frontend_session_id == frontend.session_id
    assert headers.frontend_instance_id == frontend.id
    assert headers.device_profile_id == frontend.device_profile.id
    assert headers.trace_id == "trace-123"


def test_register_trace_updates_matrix(tmp_path):
    store = SessionGraphStore(tmp_path / "graph.json")
    controller = MultiFrontendSessionController(store)
    topology = controller.create_topology(_request())
    frontend = topology.frontends[1]
    trace = controller.register_trace(RegisterCrossClientTraceRequest(root_session_id=topology.root_session_id, backend_instance_id=topology.backend.id, frontend_instance_id=frontend.id, trace_id="android-trace-1", method="POST", url="/api/orders", status_code=500, backend_route="orders.create", user_flow_id="checkout-flow"))
    matrix = controller.matrix(topology.root_session_id)

    assert trace.trace_id == "android-trace-1"
    assert matrix.trace_count == 1
    android_row = next(row for row in matrix.frontends if row.frontend_instance_id == frontend.id)
    assert android_row.latest_trace_id == "android-trace-1"
    assert android_row.os_family == OperatingSystemFamily.ANDROID
