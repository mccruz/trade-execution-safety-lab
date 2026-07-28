"""Deterministic scenario catalog and the credential-free offline demo."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable

from .adapters import VenueError, VenueErrorCategory
from .engine import ExecutionPolicy, SafeExecutionEngine
from .models import (
    Instrument,
    OrderIntent,
    OrderStatus,
    OrderType,
    PositionSnapshot,
    ReceiptOutcome,
)
from .receipts import (
    AtomicReceiptStore,
    prepare_output_directory,
    write_json_artifact,
    write_text_artifact,
)
from .recovery import plan_recovery
from .restart import inspect_restart
from .simulator import SimulatedOrderPlan, SimulatedVenue, SimulationStep
from .toy_signal import alternating_fixture_side


DEMO_INSTRUMENT = Instrument(
    symbol="DEMO-USD",
    price_tick=Decimal("0.05"),
    quantity_step=Decimal("1"),
    minimum_quantity=Decimal("1"),
    minimum_notional=Decimal("10"),
)


@dataclass(frozen=True)
class ScenarioRuntime:
    intent: OrderIntent
    venue: SimulatedVenue
    expected_positions: dict[str, Decimal]
    policy: ExecutionPolicy


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    description: str
    expected_outcome: ReceiptOutcome
    build: Callable[[], ScenarioRuntime]


def _intent(
    suffix: str,
    *,
    quantity: str = "2",
    price: str = "25.00",
    fixture_sequence: int = 0,
) -> OrderIntent:
    return OrderIntent(
        client_order_id=f"DEMO-{suffix}",
        instrument=DEMO_INSTRUMENT,
        side=alternating_fixture_side(fixture_sequence),
        order_type=OrderType.LIMIT,
        quantity=Decimal(quantity),
        limit_price=Decimal(price),
    )


def _runtime(
    suffix: str,
    plan: SimulatedOrderPlan,
    *,
    quantity: str = "2",
    initial_positions: tuple[PositionSnapshot, ...] = (),
    expected_positions: dict[str, Decimal] | None = None,
    maximum_order_polls: int = 2,
    maximum_cancel_polls: int = 2,
) -> ScenarioRuntime:
    intent = _intent(suffix, quantity=quantity)
    return ScenarioRuntime(
        intent=intent,
        venue=SimulatedVenue(
            plans={intent.client_order_id: plan},
            initial_positions=initial_positions,
        ),
        expected_positions=dict(expected_positions or {}),
        policy=ExecutionPolicy(
            maximum_order_polls=maximum_order_polls,
            maximum_cancel_polls=maximum_cancel_polls,
        ),
    )


def _full_fill() -> ScenarioRuntime:
    return _runtime(
        "FULL-FILL",
        SimulatedOrderPlan(poll_steps=(SimulationStep.fill("2", "25.00", fee="0.04"),)),
    )


def _partial_fill_cancel() -> ScenarioRuntime:
    return _runtime(
        "PARTIAL-CANCEL",
        SimulatedOrderPlan(
            poll_steps=(
                SimulationStep.fill("1", "25.00", fee="0.02"),
                SimulationStep.no_change("order-remains-open"),
            ),
        ),
    )


def _cancel_fill_race() -> ScenarioRuntime:
    return _runtime(
        "CANCEL-RACE",
        SimulatedOrderPlan(
            poll_steps=(SimulationStep.no_change("awaiting-cancel"),),
            cancel_steps=(SimulationStep.fill("2", "25.05", fee="0.04"),),
        ),
        maximum_order_polls=1,
    )


def _unresolved_cancel() -> ScenarioRuntime:
    return _runtime(
        "UNRESOLVED",
        SimulatedOrderPlan(
            poll_steps=(SimulationStep.no_change("order-still-open"),),
            cancel_steps=(
                SimulationStep.no_change("cancel-pending"),
                SimulationStep.no_change("cancel-still-pending"),
            ),
        ),
        maximum_order_polls=1,
        maximum_cancel_polls=1,
    )


def _rejected() -> ScenarioRuntime:
    return _runtime(
        "REJECTED",
        SimulatedOrderPlan(
            submit_status=OrderStatus.REJECTED,
            submit_reason="synthetic-policy-rejection",
        ),
    )


def _position_drift() -> ScenarioRuntime:
    return _runtime(
        "POSITION-DRIFT",
        SimulatedOrderPlan(),
        initial_positions=(
            PositionSnapshot(
                symbol=DEMO_INSTRUMENT.symbol,
                quantity=Decimal("3"),
                average_price=Decimal("24.50"),
                sequence=1,
            ),
        ),
    )


def _invalid_minimum() -> ScenarioRuntime:
    return _runtime(
        "INVALID-MINIMUM",
        SimulatedOrderPlan(),
        quantity="0",
    )


def _transient_disconnect() -> ScenarioRuntime:
    return _runtime(
        "DISCONNECT",
        SimulatedOrderPlan(
            poll_steps=(SimulationStep.disconnect(),),
        ),
        maximum_order_polls=1,
    )


SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        "full-fill",
        "A complete fill reconciles and authorizes the synthetic workflow to continue.",
        ReceiptOutcome.FILLED,
        _full_fill,
    ),
    ScenarioSpec(
        "partial-fill-cancel",
        "A partial fill followed by cancellation records exposure and defers.",
        ReceiptOutcome.PARTIAL_FILL_DEFERRED,
        _partial_fill_cancel,
    ),
    ScenarioSpec(
        "cancel-fill-race",
        "A fill arriving during cancellation is treated as filled, not cancelled.",
        ReceiptOutcome.FILLED,
        _cancel_fill_race,
    ),
    ScenarioSpec(
        "unresolved-cancel",
        "An unconfirmed cancel reaches a bounded fail-closed outcome.",
        ReceiptOutcome.UNKNOWN_DEFERRED,
        _unresolved_cancel,
    ),
    ScenarioSpec(
        "rejected-order",
        "A venue rejection is terminal and never retried automatically.",
        ReceiptOutcome.REJECTED,
        _rejected,
    ),
    ScenarioSpec(
        "position-drift",
        "Venue position drift blocks submission before the order API is called.",
        ReceiptOutcome.RECONCILIATION_BLOCKED,
        _position_drift,
    ),
    ScenarioSpec(
        "invalid-minimum",
        "An invalid quantity is rejected locally before any venue access.",
        ReceiptOutcome.VALIDATION_BLOCKED,
        _invalid_minimum,
    ),
    ScenarioSpec(
        "transient-disconnect",
        "A connection interruption records an unconfirmed state and stops.",
        ReceiptOutcome.VENUE_DEFERRED,
        _transient_disconnect,
    ),
)


def scenario_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in SCENARIOS)


def scenario_catalog() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "name": spec.name,
            "description": spec.description,
            "expected_outcome": spec.expected_outcome.value,
        }
        for spec in SCENARIOS
    )


def run_demo(
    output_dir: str | Path,
    *,
    reset: bool,
    selected_scenario: str | None = None,
) -> dict[str, object]:
    root = prepare_output_directory(output_dir, reset=reset)
    store = AtomicReceiptStore(root / "receipts")
    selected = tuple(
        spec
        for spec in SCENARIOS
        if selected_scenario is None or spec.name == selected_scenario
    )
    if not selected:
        raise ValueError(f"unknown scenario: {selected_scenario}")

    results: list[dict[str, object]] = []
    restart_evidence: dict[str, object] | None = None
    for spec in selected:
        runtime = spec.build()
        engine = SafeExecutionEngine(
            runtime.venue,
            expected_positions=runtime.expected_positions,
            receipt_store=store,
            policy=runtime.policy,
        )
        receipt = engine.execute(runtime.intent, scenario=spec.name)
        passed = receipt.outcome is spec.expected_outcome
        results.append(
            {
                "name": spec.name,
                "description": spec.description,
                "expected_outcome": spec.expected_outcome.value,
                "actual_outcome": receipt.outcome.value,
                "passed": passed,
                "network_used": False,
                "submit_count": runtime.venue.submit_count,
                "cancel_count": runtime.venue.cancel_count,
                "receipt": f"receipts/{runtime.intent.client_order_id}.json",
                "receipt_id": receipt.receipt_id,
            }
        )
        if spec.name == "full-fill":
            decision = inspect_restart(
                store,
                runtime.venue,
                runtime.intent.client_order_id,
            )
            restart_evidence = decision.to_dict()

    outcome_counts = Counter(str(result["actual_outcome"]) for result in results)
    recovery_evidence = {
        "transient_attempt_1": plan_recovery(
            TimeoutError("synthetic timeout"),
            attempt=1,
        ).to_dict(),
        "transient_after_budget": plan_recovery(
            TimeoutError("synthetic timeout"),
            attempt=4,
        ).to_dict(),
        "authentication_failure": plan_recovery(
            VenueError(
                "synthetic authentication failure",
                category=VenueErrorCategory.AUTHENTICATION,
            ),
            attempt=1,
        ).to_dict(),
    }
    passed = all(bool(result["passed"]) for result in results)
    summary: dict[str, object] = {
        "schema_version": 1,
        "lab": "trade-execution-safety-lab",
        "mode": "offline-simulation",
        "network_used": False,
        "credentials_required": False,
        "passed": passed,
        "scenario_count": len(results),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "scenarios": results,
        "restart_evidence": restart_evidence,
        "recovery_evidence": recovery_evidence,
        "safety_controls": [
            "pre-submission validation",
            "venue-as-source-of-truth position reconciliation",
            "idempotent client order identifiers",
            "bounded order and cancellation observation",
            "atomic checksummed receipts",
            "restart duplicate-submission suppression",
            "manual review for uncertain states",
        ],
    }
    write_json_artifact(root, "summary.json", summary)
    write_text_artifact(root, "summary.md", _render_markdown_summary(summary))
    return summary


def _render_markdown_summary(summary: dict[str, object]) -> str:
    status = "PASS" if summary["passed"] else "FAIL"
    rows = [
        "| Scenario | Expected | Actual | Result |",
        "| --- | --- | --- | --- |",
    ]
    for result in summary["scenarios"]:  # type: ignore[union-attr]
        rows.append(
            "| {name} | {expected_outcome} | {actual_outcome} | {result} |".format(
                **result,
                result="Pass" if result["passed"] else "Fail",
            )
        )
    return "\n".join(
        [
            "# Offline execution-safety demo",
            "",
            f"Overall result: **{status}**",
            "",
            "This evidence was generated with synthetic data, no network access, "
            "and no credentials.",
            "",
            *rows,
            "",
            "Checksummed receipts are in the `receipts/` directory.",
            "",
        ]
    )
