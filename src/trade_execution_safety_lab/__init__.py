"""Deterministic, offline trade-execution safety simulations."""

from .conformance import (
    ConformanceIssue,
    ConformingVenue,
    order_snapshot_issues,
    order_transition_issues,
    position_snapshot_issues,
)
from .engine import ExecutionPolicy, SafeExecutionEngine
from .models import (
    OFFLINE_SIMULATION_PROFILE,
    ExecutionReceipt,
    Fill,
    Instrument,
    OrderIntent,
    OrderSnapshot,
    OrderStatus,
    OrderType,
    PositionSnapshot,
    ReceiptOutcome,
    Side,
    VenueSafetyProfile,
)
from .simulator import SimulatedOrderPlan, SimulatedVenue, SimulationStep

__all__ = [
    "OFFLINE_SIMULATION_PROFILE",
    "ConformanceIssue",
    "ConformingVenue",
    "ExecutionPolicy",
    "ExecutionReceipt",
    "Fill",
    "Instrument",
    "OrderIntent",
    "OrderSnapshot",
    "OrderStatus",
    "OrderType",
    "PositionSnapshot",
    "ReceiptOutcome",
    "SafeExecutionEngine",
    "Side",
    "SimulatedOrderPlan",
    "SimulatedVenue",
    "SimulationStep",
    "VenueSafetyProfile",
    "order_snapshot_issues",
    "order_transition_issues",
    "position_snapshot_issues",
]

__version__ = "1.1.0"
