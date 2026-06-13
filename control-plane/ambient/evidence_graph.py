from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambient.types import AmbientEvent, EvidenceEdge, EvidenceGraphSnapshot, EvidenceNode


class EvidenceGraph:
    """Small JSON-serializable evidence graph.

    This is intentionally simple for the scaffold. It gives the control plane a
    causal model before introducing a graph database.
    """

    def __init__(self, session_id: str):
        self.snapshot = EvidenceGraphSnapshot(session_id=session_id)
        self._node_ids: set[str] = set()

    def add_event(self, event: AmbientEvent) -> None:
        session_node = self._add_node(
            f"session:{event.session_id}", "session", event.session_id, {}
        )
        event_node = self._add_node(
            f"event:{event.event_id}", "ambient_event", str(event.event_type), {
                "event_id": event.event_id,
                "source": str(event.source),
                "timestamp": event.timestamp,
            }
        )
        self._add_edge(session_node.node_id, event_node.node_id, "contains_event", event.confidence)

        payload = event.payload
        page = payload.get("page") if isinstance(payload.get("page"), dict) else {}
        self._link_payload_entity(event_node, "url", "browser_url", payload.get("url") or page.get("url"), "observed_url")
        self._link_payload_entity(event_node, "selector", "dom_node", payload.get("selector"), "observed_dom")
        self._link_payload_entity(event_node, "command", "terminal_command", payload.get("command"), "observed_command")
        self._link_payload_entity(event_node, "path", "source_file", payload.get("path"), "mentions_file")
        self._link_payload_entity(event_node, "source", "source_file", payload.get("source"), "mentions_file")

        component = payload.get("component")
        if isinstance(component, dict):
            self._link_component(event_node, component, event.confidence)

        selection = payload.get("selection")
        if isinstance(selection, dict):
            self._link_browser_selection(event_node, selection, event.confidence)

        page_state = payload.get("page_state")
        if isinstance(page_state, dict):
            self._link_browser_page_state(event_node, page_state, event.confidence)

        mentioned = payload.get("mentioned_files")
        if isinstance(mentioned, list):
            for path in mentioned:
                if isinstance(path, str):
                    self._link_payload_entity(event_node, "mentioned_files", "source_file", path, "mentions_file")

    def _link_component(self, event_node: EvidenceNode, component: dict[str, Any], confidence: float) -> None:
        component_name = component.get("name") or component.get("componentName")
        component_source = component.get("source") or component.get("sourceFile")
        if component_name:
            component_node = self._add_node(
                f"component:{component_name}", "component", component_name, component
            )
            self._add_edge(event_node.node_id, component_node.node_id, "observed_component", confidence)
            if component_source:
                file_node = self._add_node(
                    f"file:{component_source}", "source_file", component_source, {"path": component_source}
                )
                self._add_edge(component_node.node_id, file_node.node_id, "defined_in", confidence)

    def _link_browser_selection(self, event_node: EvidenceNode, selection: dict[str, Any], confidence: float) -> None:
        elements = selection.get("elements")
        if not isinstance(elements, list):
            return
        for index, element in enumerate(elements):
            if not isinstance(element, dict):
                continue
            self._link_browser_element(event_node, _merge_source_hint(element), confidence, index=index)

    def _link_browser_page_state(self, event_node: EvidenceNode, page_state: dict[str, Any], confidence: float) -> None:
        seen: set[tuple[str, str, str, str]] = set()
        for key in ("interactive", "buttons"):
            values = page_state.get(key)
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                if not isinstance(value, dict):
                    continue
                element = _merge_source_hint(value)
                identity = (
                    str(element.get("selector") or ""),
                    str(element.get("testId") or ""),
                    str(element.get("text") or ""),
                    str(element.get("sourceFile") or element.get("source") or ""),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                self._link_browser_element(event_node, element, confidence, index=index, source_kind="page_state")

    def _link_browser_element(
        self,
        event_node: EvidenceNode,
        element: dict[str, Any],
        confidence: float,
        *,
        index: int,
        source_kind: str = "selection",
    ) -> None:
        selector = element.get("selector")
        if not selector and element.get("testId"):
            selector = f"[data-testid={element['testId']}]"
        if isinstance(selector, str) and selector:
            selector_node = self._add_node(
                f"dom:{selector}",
                "dom_node",
                selector,
                {
                    "selector": selector,
                    "bounds": element.get("bounds"),
                    "index": index,
                    "source_kind": source_kind,
                    "text": element.get("text"),
                    "testId": element.get("testId"),
                },
            )
            self._add_edge(event_node.node_id, selector_node.node_id, "observed_dom", confidence)
        else:
            selector_node = event_node

        component_name = element.get("componentName") or element.get("name")
        source_file = element.get("sourceFile") or element.get("source") or element.get("path")
        source_line = element.get("sourceLine") or element.get("line")
        if isinstance(component_name, str) and component_name:
            component_node = self._add_node(
                f"component:{component_name}",
                "component",
                component_name,
                {
                    "name": component_name,
                    "framework": element.get("framework"),
                    "sourceFile": source_file,
                    "sourceLine": source_line,
                    "source_kind": source_kind,
                },
            )
            self._add_edge(selector_node.node_id, component_node.node_id, "observed_component", confidence)
            if source_file:
                file_node = self._add_node(
                    f"file:{source_file}", "source_file", source_file, {"path": source_file, "line": source_line}
                )
                self._add_edge(component_node.node_id, file_node.node_id, "defined_in", confidence)
        elif source_file:
            file_node = self._add_node(
                f"file:{source_file}", "source_file", source_file, {"path": source_file, "line": source_line}
            )
            self._add_edge(selector_node.node_id, file_node.node_id, "mentions_file", confidence)

    def _link_payload_entity(
        self,
        event_node: EvidenceNode,
        key: str,
        kind: str,
        value: Any,
        relation: str,
    ) -> None:
        if not isinstance(value, str) or not value:
            return
        node = self._add_node(f"{kind}:{value}", kind, value, {key: value})
        self._add_edge(event_node.node_id, node.node_id, relation, 1.0)

    def _add_node(self, node_id: str, kind: str, label: str, data: dict[str, Any]) -> EvidenceNode:
        if node_id in self._node_ids:
            for node in self.snapshot.nodes:
                if node.node_id == node_id:
                    return node
        node = EvidenceNode(node_id=node_id, kind=kind, label=label, data=data)
        self.snapshot.nodes.append(node)
        self._node_ids.add(node_id)
        return node

    def _add_edge(self, source_id: str, target_id: str, relation: str, confidence: float) -> None:
        edge = EvidenceEdge(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            confidence=confidence,
        )
        self.snapshot.edges.append(edge)


def _merge_source_hint(element: dict[str, Any]) -> dict[str, Any]:
    merged = dict(element)
    hint = merged.get("sourceHint") or merged.get("source_hint")
    if isinstance(hint, dict):
        for key in ("sourceFile", "source_file", "source", "path", "sourceLine", "line", "componentName"):
            value = hint.get(key)
            if value not in (None, "") and not merged.get(key):
                merged[key] = value
    if merged.get("source_file") and not merged.get("sourceFile"):
        merged["sourceFile"] = merged["source_file"]
    if merged.get("line") and not merged.get("sourceLine"):
        merged["sourceLine"] = merged["line"]
    if not merged.get("selector") and merged.get("testId"):
        merged["selector"] = f"[data-testid={merged['testId']}]"
    return merged


def build_evidence_graph(events: list[AmbientEvent]) -> EvidenceGraphSnapshot:
    session_id = events[-1].session_id if events else ""
    graph = EvidenceGraph(session_id=session_id)
    for event in events:
        graph.add_event(event)
    return graph.snapshot


def write_evidence_graph(
    events: list[AmbientEvent],
    sessions_dir: str | Path = "/opt/workstation/sessions",
) -> EvidenceGraphSnapshot:
    graph = build_evidence_graph(events)
    if not graph.session_id:
        return graph
    path = Path(sessions_dir) / graph.session_id / "ambient"
    path.mkdir(parents=True, exist_ok=True)
    target = path / "evidence_graph.json"
    target.write_text(json.dumps(graph.model_dump(), indent=2, sort_keys=True))
    return graph
