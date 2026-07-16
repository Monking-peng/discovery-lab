from __future__ import annotations

import argparse
from pathlib import Path

from discovery_lab.services.evaluation_reporting import EvaluationReportingService


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the repository Bad Case Inbox")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    inbox = EvaluationReportingService().bad_case_inbox()
    payload = inbox.model_dump_json(indent=2)
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
