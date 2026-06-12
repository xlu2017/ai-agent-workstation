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
        self._link_payload_entity(event_node, "url", "browser_url", payload.get("url"), "observed_url")
        self._link_payload_entity(event_node, "selector", "dom_node", payload.get("selector"), "observed_dom")
        self._link_payload_entity(event_node, "command", "terminal_command", payload.get("command"), "observed_command")
        self._link_payload_entity(event_node, "path", "source_file", payload.get("path"), "mentions_file")
        self._link_payload_entity(event_node, "source", "source_file", payload.get("source"), "mentions_file")

        component = payload.get("component")
        if isinstance(component, dict):
            component_name = component.get("name")
            component_source = component.get("source")
            if component_name:
                component_node = self._add_node(
                    f"component:{component_name}", "component", component_name, component
                )
                self._add_edge(event_node.node_id, component_node.node_id, "observed_component", event.confidence)
                if component_source:
                    file_node = self._add_node(
                        f"file:{component_source}", "source_file", component_source, {"path": component_source}
                    )
                    self._add_edge(component_node.node_id, file_node.node_id, "defined_in", event.confidence)

        mentioned = payload.get("mentioned_files")
        if isinstance(mentioned, list):
            for path in mentioned:
                if isinstance(path, str):
                    self._link_payload_entity(event_node, "mentioned_files", "source_file", path, "mentions_file")

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
