from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from trade_execution_safety_lab.engine import ExecutionPolicy, SafeExecutionEngine
from trade_execution_safety_lab.models import (
    Instrument,
    OrderIntent,
    OrderType,
    Side,
)
from trade_execution_safety_lab.receipts import AtomicReceiptStore, prepare_output_directory
from trade_execution_safety_lab.simulator import SimulatedOrderPlan, SimulatedVenue


INSTRUMENT = Instrument(
    symbol="DEMO-USD",
    price_tick=Decimal("0.05"),
    quantity_step=Decimal("1"),
    minimum_quantity=Decimal("1"),
    minimum_notional=Decimal("10"),
)


def make_intent(
    client_order_id: str = "TEST-ORDER",
    *,
    side: Side = Side.BUY,
    order_type: OrderType = OrderType.LIMIT,
    quantity: str = "2",
    limit_price: str | None = "25.00",
    reference_price: str | None = None,
) -> OrderIntent:
    return OrderIntent(
        client_order_id=client_order_id,
        instrument=INSTRUMENT,
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        limit_price=Decimal(limit_price) if limit_price is not None else None,
        reference_price=(
            Decimal(reference_price) if reference_price is not None else None
        ),
    )


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output_root = prepare_output_directory(
            Path(self.temporary.name) / "output",
            reset=False,
        )
        self.store = AtomicReceiptStore(self.output_root / "receipts")

    def make_engine(
        self,
        *,
        plan: SimulatedOrderPlan | None = None,
        venue: SimulatedVenue | None = None,
        expected_positions: dict[str, Decimal] | None = None,
        policy: ExecutionPolicy | None = None,
    ) -> tuple[SafeExecutionEngine, SimulatedVenue]:
        selected_venue = venue or SimulatedVenue(default_plan=plan)
        return (
            SafeExecutionEngine(
                selected_venue,
                expected_positions=expected_positions,
                receipt_store=self.store,
                policy=policy,
            ),
            selected_venue,
        )
