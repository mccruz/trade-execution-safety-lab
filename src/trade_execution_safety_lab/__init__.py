"""Deterministic, offline trade-execution safety simulations."""

from .engine import ExecutionPolicy, SafeExecutionEngine
from .models import (
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
)
from .simulator import SimulatedOrderPlan, SimulatedVenue, SimulationStep

__all__ = [
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
]

__version__ = "1.0.0"
