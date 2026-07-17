"""Typed two-phase discovery workflow with a server-enforced human gate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable


class DiscoveryWorkflowState(TypedDict, total=False):
    """Checkpoint-safe state containing IDs, hashes, and bounded summaries only."""

    phase: Literal["start", "resume"]
    run_id: str
    goal: str
    claim_revision_id: str
    claim_statement: str
    retrieval_query: str
    retrieval_purpose: str
    retrieval_limit: int
    requested_tool: str
    requested_tool_arguments: dict[str, Any]
    approval_decision: Literal["APPROVE", "REJECT"]
    plan: dict[str, Any]
    prompt_profile: dict[str, Any]
    context_manifest_id: str
    context_manifest_hash: str
    context_item_count: int
    context_items: list[dict[str, Any]]
    hypothesis: dict[str, Any]
    proposed_tool_name: str
    proposed_tool_arguments: dict[str, Any]
    tool_result: dict[str, Any]
    execution_prevented: bool
    stage: str


@runtime_checkable
class DiscoveryToolPort(Protocol):
    def retrieve_context(
        self,
        state: DiscoveryWorkflowState,
    ) -> Mapping[str, Any]: ...

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]: ...


def create_discovery_graph_builder(*, port: DiscoveryToolPort) -> Any:
    """Build a graph whose start phase cannot reach the write-tool node."""

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover - dependency setup failure
        raise RuntimeError("discovery graph requires the langgraph package") from exc

    def route_start(state: DiscoveryWorkflowState) -> str:
        if state.get("phase") == "start":
            return "plan"
        return "execute" if state.get("approval_decision") == "APPROVE" else "reject"

    def plan_node(state: DiscoveryWorkflowState) -> Mapping[str, Any]:
        return {
            "plan": {
                "steps": [
                    "retrieve_reviewed_evidence",
                    "draft_falsifiable_hypothesis",
                    "request_exact_tool_approval",
                ],
                "goal": state["goal"],
                "claim_revision_id": state["claim_revision_id"],
            },
            "prompt_profile": {
                "name": "opportunity-discovery-agent",
                "version": "1.0.0",
                "system_prompt_version": "discovery-agent-system.v1",
                "source_content_handling": "untrusted_data_only",
                "context_policy": "exact_context_manifest_only",
                "tool_policy": "server_allowlist_and_exact_argument_approval",
                "model": "deterministic-portfolio-harness",
                "model_called": False,
            },
            "stage": "planned",
        }

    def retrieve_node(state: DiscoveryWorkflowState) -> Mapping[str, Any]:
        result = dict(port.retrieve_context(state))
        return {**result, "stage": "context_retrieved"}

    def draft_node(state: DiscoveryWorkflowState) -> Mapping[str, Any]:
        requested = state["requested_tool_arguments"]
        metric = str(requested.get("primary_metric", "the declared primary metric"))
        threshold = str(requested.get("success_threshold", "the declared threshold"))
        cohort = str(requested.get("target_cohort", "the target cohort"))
        return {
            "hypothesis": {
                "statement": (
                    f"For {cohort}, a bounded pilot addressing '{state['claim_statement']}' "
                    f"will improve {metric}."
                ),
                "expected_outcome": threshold,
                "falsification_criterion": (
                    f"Reject or revise the hypothesis if {metric} does not meet {threshold}."
                ),
                "falsifiable": True,
                "claim_revision_id": state["claim_revision_id"],
                "context_manifest_id": state["context_manifest_id"],
            },
            "stage": "hypothesis_drafted",
        }

    def propose_node(state: DiscoveryWorkflowState) -> Mapping[str, Any]:
        arguments = {
            **state["requested_tool_arguments"],
            "claim_revision_id": state["claim_revision_id"],
            "context_manifest_id": state["context_manifest_id"],
            "hypothesis": state["hypothesis"],
        }
        return {
            "proposed_tool_name": state["requested_tool"],
            "proposed_tool_arguments": arguments,
            "stage": "waiting_human",
        }

    def execute_node(state: DiscoveryWorkflowState) -> Mapping[str, Any]:
        result = port.execute_tool(
            state["proposed_tool_name"],
            state["proposed_tool_arguments"],
        )
        return {"tool_result": result, "execution_prevented": False, "stage": "completed"}

    def reject_node(_state: DiscoveryWorkflowState) -> Mapping[str, Any]:
        return {"execution_prevented": True, "stage": "rejected"}

    builder: Any = StateGraph(DiscoveryWorkflowState)
    builder.add_node("plan", plan_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("draft", draft_node)
    builder.add_node("propose", propose_node)
    builder.add_node("execute", execute_node)
    builder.add_node("reject", reject_node)
    builder.add_conditional_edges(
        START,
        route_start,
        {"plan": "plan", "execute": "execute", "reject": "reject"},
    )
    builder.add_edge("plan", "retrieve")
    builder.add_edge("retrieve", "draft")
    builder.add_edge("draft", "propose")
    builder.add_edge("propose", END)
    builder.add_edge("execute", END)
    builder.add_edge("reject", END)
    return builder


def compile_discovery_graph(
    *,
    port: DiscoveryToolPort,
    checkpointer: Any | None = None,
) -> Any:
    return create_discovery_graph_builder(port=port).compile(checkpointer=checkpointer)
