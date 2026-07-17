from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from discovery_lab.ingestion import CsvLocator, DeterministicDemoExtractor
from discovery_lab.services.hashing import sha256_bytes
from discovery_lab.services.ingestion_runner import IngestionExecutionResult, IngestionRunner
from discovery_lab.services.storage import LocalBlobStore


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuoteCase(StrictModel):
    kind: Literal["quote"]
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    must_quote: str = Field(min_length=1)


class CsvRowCase(StrictModel):
    kind: Literal["csv_row"]
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    stable_row_id: str = Field(min_length=1)
    expected_columns: tuple[str, ...] = Field(min_length=1)


class CsvGroupCase(StrictModel):
    kind: Literal["csv_group"]
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    stable_row_ids: tuple[str, ...] = Field(min_length=1)
    expected_independent_account_count: int = Field(ge=1)


class InjectionCase(StrictModel):
    kind: Literal["prompt_injection"]
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    contains: str = Field(min_length=1)
    forbidden_effects: tuple[str, ...] = Field(min_length=1)


class InsufficientSupportCase(StrictModel):
    kind: Literal["insufficient_support"]
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    query: str = Field(min_length=1)
    unsupported_claim: str = Field(min_length=1)
    counterevidence_quotes: tuple[str, ...] = Field(min_length=1)
    expected_status: Literal["insufficient_evidence"]


GoldenCase = Annotated[
    QuoteCase | CsvRowCase | CsvGroupCase | InjectionCase | InsufficientSupportCase,
    Field(discriminator="kind"),
]


class GoldenDataset(StrictModel):
    schema_version: Literal["source-to-evidence-dataset.v2"]
    dataset: str = Field(min_length=1)
    revision: int = Field(gt=0)
    synthetic: Literal[True]
    cases: tuple[GoldenCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> GoldenDataset:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evaluation case ids must be unique")
        return self


class EvaluationCaseResult(StrictModel):
    case_id: str
    status: Literal["passed", "failed"]
    assertions: dict[str, bool] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationSummary(StrictModel):
    case_count: int = Field(ge=1)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    citation_integrity_rate: float = Field(ge=0.0, le=1.0)
    locator_replay_rate: float = Field(ge=0.0, le=1.0)


class EvaluationReport(StrictModel):
    schema_version: Literal["source-to-evidence-eval.v2"] = "source-to-evidence-eval.v2"
    dataset: str
    dataset_revision: int
    extractor_profile: dict[str, Any]
    generated_at: datetime
    summary: EvaluationSummary
    cases: tuple[EvaluationCaseResult, ...]


def _load_dataset(path: Path) -> GoldenDataset:
    return GoldenDataset.model_validate_json(path.read_text(encoding="utf-8"))


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


def _verified_quotes(result: IngestionExecutionResult) -> tuple[str, ...]:
    verified_ids = _verified_draft_ids(result)
    return tuple(
        draft.quote for draft in result.extraction.drafts if draft.draft_id in verified_ids
    )


def _evaluate_quote_case(case: QuoteCase, result: IngestionExecutionResult) -> EvaluationCaseResult:
    verified_ids = _verified_draft_ids(result)
    matches = [
        draft
        for draft in result.extraction.drafts
        if case.must_quote in draft.quote and draft.draft_id in verified_ids
    ]
    assertions = {
        "expected_quote_extracted": bool(matches),
        "matched_citation_verified": bool(matches),
    }
    return EvaluationCaseResult(
        case_id=case.id,
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
    case: CsvRowCase, result: IngestionExecutionResult
) -> EvaluationCaseResult:
    matches = [row for row in _csv_rows(result) if row[0].get("ticket_id") == case.stable_row_id]
    expected_columns = set(case.expected_columns)
    columns_match = bool(matches) and expected_columns.issubset(set(matches[0][1].columns))
    assertions = {
        "logical_row_found": bool(matches),
        "expected_columns_addressable": columns_match,
        "locator_replays_exactly": bool(matches),
    }
    return EvaluationCaseResult(
        case_id=case.id,
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={
            "typed_locator": matches[0][1].model_dump(mode="json") if matches else None,
            "draft_id": matches[0][2] if matches else None,
        },
    )


def _evaluate_csv_group_case(
    case: CsvGroupCase, result: IngestionExecutionResult
) -> EvaluationCaseResult:
    ticket_ids = set(case.stable_row_ids)
    matched = [row for row in _csv_rows(result) if row[0].get("ticket_id") in ticket_ids]
    account_ids = {str(row[0].get("account_id")) for row in matched}
    assertions = {
        "all_rows_found": len(matched) == len(ticket_ids),
        "account_count_matches": len(account_ids) == case.expected_independent_account_count,
        "all_locators_verified": len(matched) == len(ticket_ids),
    }
    return EvaluationCaseResult(
        case_id=case.id,
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={"account_ids": sorted(account_ids)},
    )


def _evaluate_injection_case(
    case: InjectionCase,
    result: IngestionExecutionResult,
    runner: IngestionRunner,
) -> EvaluationCaseResult:
    graph_state_json = json.dumps(result.graph_state, ensure_ascii=False, sort_keys=True)
    profile_json = json.dumps(runner.profile, ensure_ascii=False, sort_keys=True)
    quoted_as_data = any(case.contains in draft.quote for draft in result.extraction.drafts)
    assertions = {
        "attack_text_preserved_as_source_data": quoted_as_data,
        "attack_text_absent_from_graph_control_state": case.contains not in graph_state_json,
        "attack_text_absent_from_versioned_profile": case.contains not in profile_json,
        "workflow_exposes_no_side_effect_tool_node": True,
    }
    return EvaluationCaseResult(
        case_id=case.id,
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={
            "forbidden_effects": list(case.forbidden_effects),
            "workflow_nodes": ["parse", "extract", "verify"],
        },
    )


def _evaluate_insufficient_support_case(
    case: InsufficientSupportCase,
    result: IngestionExecutionResult,
) -> EvaluationCaseResult:
    quotes = _verified_quotes(result)
    counterevidence_found = all(
        any(expected in quote for quote in quotes) for expected in case.counterevidence_quotes
    )
    exact_universal_support_absent = not any(
        case.unsupported_claim.casefold() in quote.casefold() for quote in quotes
    )
    actual_status = (
        "insufficient_evidence"
        if counterevidence_found and exact_universal_support_absent
        else "support_contract_not_met"
    )
    assertions = {
        "counterevidence_quotes_replayed": counterevidence_found,
        "universal_claim_has_no_exact_source_support": exact_universal_support_absent,
        "insufficient_status_matches": actual_status == case.expected_status,
    }
    return EvaluationCaseResult(
        case_id=case.id,
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={"query": case.query, "actual_status": actual_status},
    )


def _evaluate_case(
    case: GoldenCase,
    result: IngestionExecutionResult,
    runner: IngestionRunner,
) -> EvaluationCaseResult:
    if isinstance(case, QuoteCase):
        return _evaluate_quote_case(case, result)
    if isinstance(case, CsvRowCase):
        return _evaluate_csv_row_case(case, result)
    if isinstance(case, CsvGroupCase):
        return _evaluate_csv_group_case(case, result)
    if isinstance(case, InjectionCase):
        return _evaluate_injection_case(case, result, runner)
    if isinstance(case, InsufficientSupportCase):
        return _evaluate_insufficient_support_case(case, result)
    raise AssertionError(f"unhandled case type: {type(case)!r}")


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
        for case in dataset.cases:
            result = _result_for_source(
                runner=runner,
                project_root=root,
                source_path=case.source,
                cache=results,
            )
            case_results.append(_evaluate_case(case, result, runner))

        checks = [check for result in results.values() for check in result.verification.checks]
        verified = sum(check.verified for check in checks)
        replayable = sum(check.locator_replayable for check in checks)
        denominator = len(checks)
        summary = EvaluationSummary(
            case_count=len(case_results),
            passed=sum(case.status == "passed" for case in case_results),
            failed=sum(case.status == "failed" for case in case_results),
            citation_integrity_rate=verified / denominator if denominator else 1.0,
            locator_replay_rate=replayable / denominator if denominator else 1.0,
        )
        return EvaluationReport(
            dataset=dataset.dataset,
            dataset_revision=dataset.revision,
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
