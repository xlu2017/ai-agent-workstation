from pathlib import Path


EXTENSION_BACKGROUND = Path(__file__).parent.parent / "extension" / "background.js"


def test_extension_submits_region_prompt_to_session_graph_chat_first():
    source = EXTENSION_BACKGROUND.read_text()

    assert "/api/session-graph/sessions/${encodeURIComponent(sessionId)}/chat" in source
    assert "body: JSON.stringify({ content: instruction, role: 'user', mode: 'finite' })" in source
    assert "transport: 'session_graph_chat'" in source


def test_extension_keeps_legacy_chat_as_explicit_fallback():
    source = EXTENSION_BACKGROUND.read_text()

    assert "/api/sessions/${encodeURIComponent(sessionId)}/chat" in source
    assert "body: JSON.stringify({ instruction, execution_mode: 'finite' })" in source
    assert "transport: 'legacy_session_chat'" in source


def test_extension_propagates_chat_submit_failure_to_overlay():
    source = EXTENSION_BACKGROUND.read_text()

    assert "if (chatJson?.ok === false)" in source
    assert "return {\n      ok: false," in source
    assert "transport: 'none'" in source
    assert "graph_error" in source
    assert "legacy_error" in source


def test_extension_mirrors_ambient_event_to_created_child_session():
    source = EXTENSION_BACKGROUND.read_text()

    assert "const childSessionId = chatJson?.work_session?.id || chatJson?.goal_session?.id || '';" in source
    assert "childSessionId && childSessionId !== sessionId" in source
    assert "parent_ambient_event_id: ambientEventId" in source
    assert "chrome_extension.region_prompt.mirrored_to_child_session" in source
    assert "childAmbientEventId" in source
