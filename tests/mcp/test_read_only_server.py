from __future__ import annotations

from pathlib import Path

import pytest

from discovery_lab.mcp_server import mcp

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_mcp_exposes_only_explicitly_read_only_tools() -> None:
    tools = await mcp.list_tools()

    assert [tool.name for tool in tools] == [
        "list_studies",
        "list_reviewed_claims",
        "retrieve_reviewed_evidence",
        "get_context_manifest",
        "get_product_artifacts",
        "get_prd",
    ]
    assert all(tool.annotations is not None for tool in tools)
    assert all(tool.annotations.readOnlyHint is True for tool in tools if tool.annotations)
    assert all(tool.annotations.destructiveHint is False for tool in tools if tool.annotations)


def test_mcp_adapter_uses_public_api_and_has_no_business_table_access() -> None:
    source = (ROOT / "src" / "discovery_lab" / "mcp_server.py").read_text(encoding="utf-8")
    lowered = source.lower()

    assert "discovery_lab.db" not in source
    assert "sqlalchemy" not in lowered
    assert "tool-calls" not in lowered
    assert "/approvals" not in lowered
    assert 'client.post("/v1/experiments' not in lowered
    assert 'client.post("/v1/decisions' not in lowered
    assert "retrieve_reviewed_evidence" in source
    assert "/v1/context-manifests/" in source
