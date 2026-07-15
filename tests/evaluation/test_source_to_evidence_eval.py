from pathlib import Path

from discovery_lab.evaluation.source_to_evidence import run_evaluation


def test_helphub_golden_dataset_passes_source_to_evidence_gate() -> None:
    project_root = Path(__file__).resolve().parents[2]

    report = run_evaluation(
        project_root / "evals" / "golden" / "source_to_evidence.json",
        project_root=project_root,
    )

    assert report.summary.failed == 0
    assert report.summary.passed == 5
    assert report.summary.skipped == 1
    assert report.summary.citation_integrity_rate == 1.0
    assert report.summary.locator_replay_rate == 1.0
    injection = next(case for case in report.cases if case.case_id == "source-prompt-injection")
    assert injection.status == "passed"
    assert all(injection.assertions.values())
