"""Command-line interface for the offline execution-safety lab."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .receipts import verify_receipt_payload
from .scenarios import run_demo, scenario_catalog, scenario_names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trade-safety-lab",
        description=(
            "Run deterministic broker/exchange execution-safety simulations. "
            "No network access or credentials are used."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser(
        "demo",
        help="Run the offline scenario suite and write checksummed evidence.",
    )
    demo.add_argument(
        "--output-dir",
        default="demo-output",
        help="Lab-owned artifact directory (default: demo-output).",
    )
    demo.add_argument(
        "--reset",
        action="store_true",
        help="Reset an existing directory only when it has the lab sentinel.",
    )
    demo.add_argument(
        "--scenario",
        choices=scenario_names(),
        help="Run one scenario instead of the complete suite.",
    )

    subparsers.add_parser(
        "list-scenarios",
        help="List the deterministic scenarios without running them.",
    )

    verify = subparsers.add_parser(
        "verify-receipt",
        help="Verify the SHA-256 digest embedded in a receipt.",
    )
    verify.add_argument("path", help="Path to a generated receipt JSON file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list-scenarios":
            for scenario in scenario_catalog():
                print(
                    f"{scenario['name']}: {scenario['description']} "
                    f"(expected: {scenario['expected_outcome']})"
                )
            return 0

        if args.command == "verify-receipt":
            payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
            valid = isinstance(payload, dict) and verify_receipt_payload(payload)
            print("Receipt verified." if valid else "Receipt verification failed.")
            return 0 if valid else 1

        summary = run_demo(
            args.output_dir,
            reset=args.reset,
            selected_scenario=args.scenario,
        )
        print(
            f"Offline demo {'passed' if summary['passed'] else 'failed'}: "
            f"{summary['scenario_count']} scenario(s), no network, no credentials."
        )
        print(f"Evidence: {Path(args.output_dir).resolve() / 'summary.md'}")
        return 0 if summary["passed"] else 1
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
