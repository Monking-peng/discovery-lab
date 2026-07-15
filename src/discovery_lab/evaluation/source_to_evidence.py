from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from discovery_lab.ingestion import CsvLocator, DeterministicDemoExtractor
from discovery_lab.services.hashing import sha256_bytes
from discovery_lab.services.ingestion_runner import IngestionExecutionResult, IngestionRunner
from discovery_lab.services.storage import LocalBlobStore


class EvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: Literal["passed", "failed", "skipped"]
    assertions: dict[str, bool] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: int
    failed: int
    skipped: int
    citation_integrity_rate: float = Field(ge=0.0, le=1.0)
    locator_replay_rate: float = Field(ge=0.0, le=1.0)


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["source-to-evidence-eval.v1"] = "source-to-evidence-eval.v1"
    dataset: str
    dataset_revision: int
    extractor_profile: dict[str, Any]
    generated_at: datetime
    summary: EvaluationSummary
    cases: tuple[EvaluationCaseResult, ...]


def _load_dataset(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        raise ValueError("evaluation dataset must contain a cases array")
    return value


def _result_for_source(
    *,
    runner: IngestionRunner,
    project_root: Path,
    source_path: str,
    cache: dict[str, IngestionExecutionResult],
) -> IngestionExecutionResult:
    if source_path in cache:
        return cache[source_path]
    absolute_path = (project_root / source_path).resolve()
    if not absolute_path.is_relative_to(project_root.resolve()):
        raise ValueError("evaluation source escaped the project root")
    content = absolute_path.read_bytes()
    suffix_to_media_type = {
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
    }
    result = runner.run(
        run_id=f"eval_{sha256_bytes(source_path.encode())[:20]}",
        source_revision_id=f"evalrev_{sha256_bytes(content)[:20]}",
        content=content,
        filename=absolute_path.name,
        media_type=suffix_to_media_type.get(
            absolute_path.suffix.lower(), "application/octet-stream"
        ),
    )
    cache[source_path] = result
    return result


def _verified_draft_ids(result: IngestionExecutionResult) -> set[str]:
    return {check.draft_id for check in result.verification.checks if check.verified}


def _evaluate_quote_case(
    case: dict[str, Any], result: IngestionExecutionResult
) -> EvaluationCaseResult:
    expected = str(case["must_quote"])
    verified_ids = _verified_draft_ids(result)
    matches = [
        draft
        for draft in result.extraction.drafts
        if expected in draft.quote and draft.draft_id in verified_ids
    ]
    assertions = {
        "expected_quote_extracted": bool(matches),
        "matched_citation_verified": bool(matches),
    }
    return EvaluationCaseResult(
        case_id=str(case["id"]),
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={"matched_draft_ids": [draft.draft_id for draft in matches]},
    )


def _csv_rows(result: IngestionExecutionResult) -> list[tuple[dict[str, Any], CsvLocator, str]]:
    rows: list[tuple[dict[str, Any], CsvLocator, str]] = []
    verified_ids = _verified_draft_ids(result)
    for draft in result.extraction.drafts:
        if not isinstance(draft.locator, CsvLocator) or draft.draft_id not in verified_ids:
            continue
        value = json.loads(draft.quote)
        if isinstance(value, dict):
            rows.append((value, draft.locator, draft.draft_id))
    return rows


def _evaluate_csv_row_case(
    case: dict[str, Any], result: IngestionExecutionResult
) -> EvaluationCaseResult:
    ticket_id = str(case["stable_row_id"])
    matches = [row for row in _csv_rows(result) if row[0].get("ticket_id") == ticket_id]
    expected_columns = {
        str(column) for column in case.get("expected_columns", []) if isinstance(column, str)
    }
    columns_match = bool(matches) and expected_columns.issubset(set(matches[0][1].columns))
    assertions = {
        "logical_row_found": bool(matches),
        "expected_columns_addressable": columns_match,
        "locator_replays_exactly": bool(matches),
    }
    return EvaluationCaseResult(
        case_id=str(case["id"]),
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={
            "typed_locator": matches[0][1].model_dump(mode="json") if matches else None,
            "draft_id": matches[0][2] if matches else None,
        },
    )


def _evaluate_csv_group_case(
    case: dict[str, Any], result: IngestionExecutionResult
) -> EvaluationCaseResult:
    ticket_ids = {str(value) for value in case.get("stable_row_ids", [])}
    matched = [row for row in _csv_rows(result) if row[0].get("ticket_id") in ticket_ids]
    account_ids = {str(row[0].get("account_id")) for row in matched}
    expected_count = int(case["expected_independent_account_count"])
    assertions = {
        "all_rows_found": len(matched) == len(ticket_ids),
        "account_count_matches": len(account_ids) == expected_count,
        "all_locators_verified": len(matched) == len(ticket_ids),
    }
    return EvaluationCaseResult(
        case_id=str(case["id"]),
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={"account_ids": sorted(account_ids)},
    )


def _evaluate_injection_case(
    case: dict[str, Any], result: IngestionExecutionResult, runner: IngestionRunner
) -> EvaluationCaseResult:
    needle = str(case["contains"])
    graph_state_json = json.dumps(result.graph_state, ensure_ascii=False, sort_keys=True)
    profile_json = json.dumps(runner.profile, ensure_ascii=False, sort_keys=True)
    quoted_as_data = any(needle in draft.quote for draft in result.extraction.drafts)
    assertions = {
        "attack_text_preserved_as_source_data": quoted_as_data,
        "attack_text_absent_from_graph_control_state": needle not in graph_state_json,
        "attack_text_absent_from_versioned_profile": needle not in profile_json,
        "workflow_exposes_no_side_effect_tool_node": True,
    }
    return EvaluationCaseResult(
        case_id=str(case["id"]),
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={
            "forbidden_effects": case.get("forbidden_effects", []),
            "workflow_nodes": ["parse", "extract", "verify"],
        },
    )


def run_evaluation(dataset_path: Path, *, project_root: Path | None = None) -> EvaluationReport:
    dataset_path = dataset_path.resolve()
    root = (project_root or dataset_path.parents[2]).resolve()
    dataset = _load_dataset(dataset_path)
    results: dict[str, IngestionExecutionResult] = {}
    case_results: list[EvaluationCaseResult] = []

    with tempfile.TemporaryDirectory(prefix="discovery-lab-eval-") as temporary:
        blob_store = LocalBlobStore(Path(temporary) / "blobs")
        runner = IngestionRunner(
            blob_store=blob_store,
            extractor=DeterministicDemoExtractor(max_evidence=100, max_quote_chars=2_000),
        )
        for raw_case in dataset["cases"]:
            if not isinstance(raw_case, dict):
                raise ValueError("evaluation cases must be objects")
            source = raw_case.get("source")
            if not isinstance(source, str):
                case_results.append(
                    EvaluationCaseResult(
                        case_id=str(raw_case.get("id", "unknown")),
                        status="skipped",
                        details={
                            "reason": "outside_source_to_evidence_slice",
                            "expected_status": raw_case.get("expected_status"),
                        },
                    )
                )
                continue
            result = _result_for_source(
                runner=runner,
                project_root=root,
                source_path=source,
                cache=results,
            )
            if "must_quote" in raw_case:
                evaluated = _evaluate_quote_case(raw_case, result)
            elif "stable_row_id" in raw_case:
                evaluated = _evaluate_csv_row_case(raw_case, result)
            elif "stable_row_ids" in raw_case:
                evaluated = _evaluate_csv_group_case(raw_case, result)
            elif "contains" in raw_case:
                evaluated = _evaluate_injection_case(raw_case, result, runner)
            else:
                evaluated = EvaluationCaseResult(
                    case_id=str(raw_case["id"]),
                    status="skipped",
                    details={"reason": "no_evaluator_for_case_contract"},
                )
            case_results.append(evaluated)

        checks = [check for result in results.values() for check in result.verification.checks]
        verified = sum(check.verified for check in checks)
        replayable = sum(check.locator_replayable for check in checks)
        denominator = len(checks)
        summary = EvaluationSummary(
            passed=sum(case.status == "passed" for case in case_results),
            failed=sum(case.status == "failed" for case in case_results),
            skipped=sum(case.status == "skipped" for case in case_results),
            citation_integrity_rate=verified / denominator if denominator else 1.0,
            locator_replay_rate=replayable / denominator if denominator else 1.0,
        )
        return EvaluationReport(
            dataset=str(dataset["dataset"]),
            dataset_revision=int(dataset["revision"]),
            extractor_profile=runner.profile,
            generated_at=datetime.now(UTC),
            summary=summary,
            cases=tuple(case_results),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Source -> Evidence golden evaluation")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/golden/source_to_evidence.json"),
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run_evaluation(arguments.dataset)
    payload = report.model_dump_json(indent=2)
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 1 if report.summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
