from __future__ import annotations

from typing import Any

from discovery_lab.agent_harness.discovery_graph import compile_discovery_graph


class FakeToolPort:
    def __init__(self) -> None:
        self.retrieval_calls = 0
        self.write_calls = 0

    def retrieve_context(self, state: dict[str, Any]) -> dict[str, Any]:
        self.retrieval_calls += 1
        return {
            "context_manifest_id": "manifest-1",
            "context_manifest_hash": "a" * 64,
            "context_item_count": 2,
            "context_items": [
                {"evidence_revision_id": "evidence-revision-1", "observation": "Risk is missed."}
            ],
        }

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self.write_calls += 1
        return {"tool": tool_name, "arguments": arguments, "persisted": True}


def _start_state() -> dict[str, Any]:
    return {
        "phase": "start",
        "run_id": "run-1",
        "goal": "Reduce missed high-risk escalation",
        "claim_revision_id": "claim-revision-1",
        "claim_statement": "High-risk enterprise tickets are missed before escalation.",
        "retrieval_query": "enterprise outage escalation SLA",
        "retrieval_purpose": "support",
        "retrieval_limit": 5,
        "requested_tool": "create_experiment_draft",
        "requested_tool_arguments": {
            "title": "Risk escalation pilot",
            "primary_metric": "missed escalation rate",
            "success_threshold": "reduce by 30%",
        },
    }


def test_graph_pauses_before_write_tool_and_resumes_only_after_approval() -> None:
    port = FakeToolPort()
    graph = compile_discovery_graph(port=port)

    waiting = graph.invoke(_start_state())

    assert waiting["stage"] == "waiting_human"
    assert waiting["context_manifest_id"] == "manifest-1"
    assert waiting["proposed_tool_name"] == "create_experiment_draft"
    assert waiting["prompt_profile"]["source_content_handling"] == "untrusted_data_only"
    assert waiting["hypothesis"]["falsifiable"] is True
    assert port.retrieval_calls == 1
    assert port.write_calls == 0

    approved = graph.invoke(
        {
            **waiting,
            "phase": "resume",
            "approval_decision": "APPROVE",
        }
    )
    assert approved["stage"] == "completed"
    assert approved["tool_result"]["persisted"] is True
    assert port.write_calls == 1


def test_graph_rejection_never_executes_the_write_tool() -> None:
    port = FakeToolPort()
    graph = compile_discovery_graph(port=port)
    waiting = graph.invoke(_start_state())

    rejected = graph.invoke(
        {
            **waiting,
            "phase": "resume",
            "approval_decision": "REJECT",
        }
    )

    assert rejected["stage"] == "rejected"
    assert rejected["execution_prevented"] is True
    assert "tool_result" not in rejected
    assert port.write_calls == 0
