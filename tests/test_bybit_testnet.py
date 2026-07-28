from __future__ import annotations

from decimal import Decimal

from tests.fake_bybit import (
    FakeBybitClient,
    execution_item,
    order_item,
    position_item,
    response,
)
from tests.helpers import StoreTestCase
from trade_execution_safety_lab.adapters import VenueError, VenueErrorCategory
from trade_execution_safety_lab.conformance import ConformingVenue
from trade_execution_safety_lab.connectors.bybit_testnet import (
    BYBIT_TESTNET_API_KEY_ENV,
    BYBIT_TESTNET_API_SECRET_ENV,
    BYBIT_TESTNET_ENDPOINT,
    BybitTestnetSettings,
    BybitTestnetVenue,
)
from trade_execution_safety_lab.engine import SafeExecutionEngine
from trade_execution_safety_lab.models import (
    Instrument,
    OrderIntent,
    OrderStatus,
    OrderType,
    ReceiptOutcome,
    Side,
)


def make_testnet_intent(
    *,
    client_order_id: str = "TESTNET-ORDER-1",
    quantity: str = "0.001",
) -> OrderIntent:
    return OrderIntent(
        client_order_id=client_order_id,
        instrument=Instrument(
            symbol="BTCUSDT",
            price_tick=Decimal("0.10"),
            quantity_step=Decimal("0.001"),
            minimum_quantity=Decimal("0.001"),
            minimum_notional=Decimal("5"),
        ),
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal(quantity),
        limit_price=Decimal("50000.00"),
    )


class AuthenticationFailure(Exception):
    status_code = 10003


class RateLimitFailure(Exception):
    status_code = 10006


class BybitTestnetTests(StoreTestCase):
    def test_settings_reject_non_linear_category(self) -> None:
        with self.assertRaises(ValueError):
            BybitTestnetSettings(category="spot")

    def test_mainnet_endpoint_is_structurally_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BybitTestnetVenue(FakeBybitClient(endpoint="https://api.bybit.com"))

    def test_connector_module_does_not_require_optional_sdk_at_import(self) -> None:
        self.assertEqual(BYBIT_TESTNET_ENDPOINT, "https://api-testnet.bybit.com")

    def test_environment_factory_is_testnet_only_and_repr_is_redacted(self) -> None:
        captured: dict[str, object] = {}

        def factory(**kwargs):
            captured.update(kwargs)
            return FakeBybitClient()

        venue = BybitTestnetVenue.from_environment(
            environ={
                BYBIT_TESTNET_API_KEY_ENV: "not-a-real-key",
                BYBIT_TESTNET_API_SECRET_ENV: "not-a-real-secret",
            },
            client_factory=factory,
        )
        self.assertTrue(captured["testnet"])
        self.assertFalse(captured["demo"])
        self.assertFalse(captured["log_requests"])
        self.assertEqual(captured["max_retries"], 1)
        self.assertEqual(captured["retry_codes"], {0})
        self.assertNotIn("not-a-real", repr(venue))

    def test_missing_environment_values_are_named_without_values(self) -> None:
        with self.assertRaises(ValueError) as raised:
            BybitTestnetVenue.from_environment(
                environ={},
                client_factory=lambda **_: FakeBybitClient(),
            )
        message = str(raised.exception)
        self.assertIn(BYBIT_TESTNET_API_KEY_ENV, message)
        self.assertIn(BYBIT_TESTNET_API_SECRET_ENV, message)

    def test_client_construction_failure_does_not_copy_secret_values(self) -> None:
        def failing_factory(**kwargs):
            raise RuntimeError(str(kwargs))

        with self.assertRaises(RuntimeError) as raised:
            BybitTestnetVenue.from_environment(
                environ={
                    BYBIT_TESTNET_API_KEY_ENV: "not-a-real-key",
                    BYBIT_TESTNET_API_SECRET_ENV: "not-a-real-secret",
                },
                client_factory=failing_factory,
            )
        self.assertNotIn("not-a-real", str(raised.exception))

    def test_instrument_constraints_come_from_testnet(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        instrument = venue.instrument("BTCUSDT")
        self.assertEqual(instrument, make_testnet_intent().instrument)
        self.assertTrue(venue.network_used)

    def test_submit_uses_client_order_id_and_fixed_one_way_mode(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        order = venue.submit(make_testnet_intent())
        call = next(item for item in client.calls if item[0] == "place_order")
        self.assertEqual(call[1]["orderLinkId"], "TESTNET-ORDER-1")
        self.assertEqual(call[1]["positionIdx"], 0)
        self.assertEqual(order.status, OrderStatus.ACCEPTED)

    def test_constraint_mismatch_blocks_before_submission(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        intent = make_testnet_intent()
        mismatched = OrderIntent(
            client_order_id=intent.client_order_id,
            instrument=Instrument(
                symbol="BTCUSDT",
                price_tick=Decimal("1"),
                quantity_step=Decimal("0.001"),
                minimum_quantity=Decimal("0.001"),
                minimum_notional=Decimal("5"),
            ),
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            limit_price=intent.limit_price,
        )
        with self.assertRaises(VenueError):
            venue.submit(mismatched)
        self.assertFalse(any(name == "place_order" for name, _ in client.calls))

    def test_poll_maps_order_and_execution_history(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        venue.submit(make_testnet_intent())
        client.queue("get_open_orders", response([order_item(status="Filled")]))
        client.queue("get_executions", response([execution_item()]))
        order = venue.poll("ORDER-1")
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(order.filled_quantity, Decimal("0.001"))
        self.assertEqual(order.total_fee, Decimal("0.01"))

    def test_execution_rebate_preserves_signed_fee(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        venue.submit(make_testnet_intent())
        client.queue("get_open_orders", response([order_item(status="Filled")]))
        client.queue(
            "get_executions",
            response([execution_item(fee="-0.01")]),
        )
        order = venue.poll("ORDER-1")
        self.assertEqual(order.total_fee, Decimal("-0.01"))

    def test_unsupported_statuses_are_not_normalized_for_linear_orders(self) -> None:
        for status in (
            "Created",
            "Untriggered",
            "Triggered",
            "PartiallyFilledCanceled",
            "Deactivated",
        ):
            with self.subTest(status=status):
                client = FakeBybitClient()
                venue = BybitTestnetVenue(client)
                venue.submit(make_testnet_intent())
                client.queue(
                    "get_open_orders",
                    response([order_item(status=status)]),
                )
                order = venue.poll("ORDER-1")
                self.assertEqual(order.status, OrderStatus.UNKNOWN)

    def test_cancel_acknowledgement_is_observed(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        venue.submit(make_testnet_intent())
        client.queue("get_open_orders", response([order_item(status="Cancelled")]))
        order = venue.cancel("ORDER-1")
        self.assertEqual(order.status, OrderStatus.CANCELLED)

    def test_client_order_lookup_falls_back_to_history(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        client.queue("get_open_orders", response())
        client.queue("get_order_history", response([order_item(status="Cancelled")]))
        order = venue.find_by_client_order_id("TESTNET-ORDER-1")
        self.assertIsNotNone(order)
        assert order is not None
        self.assertEqual(order.venue_order_id, "ORDER-1")

    def test_positions_preserve_long_and_short_sign(self) -> None:
        client = FakeBybitClient()
        client.queue(
            "get_positions",
            response(
                [
                    position_item(side="Buy", symbol="BTCUSDT"),
                    position_item(side="Sell", symbol="ETHUSDT", size="0.2"),
                ]
            ),
        )
        positions = BybitTestnetVenue(client).positions()
        self.assertEqual(positions[0].quantity, Decimal("0.001"))
        self.assertEqual(positions[1].quantity, Decimal("-0.2"))

    def test_error_category_is_typed_and_exception_text_is_redacted(self) -> None:
        client = FakeBybitClient()
        client.queue(
            "get_positions",
            AuthenticationFailure("not-a-real-secret"),
        )
        with self.assertRaises(VenueError) as raised:
            BybitTestnetVenue(client).positions()
        self.assertEqual(
            raised.exception.category,
            VenueErrorCategory.AUTHENTICATION,
        )
        self.assertNotIn("not-a-real-secret", str(raised.exception))

    def test_rate_limit_is_retryable_but_not_retried_by_adapter(self) -> None:
        client = FakeBybitClient()
        client.queue("get_positions", RateLimitFailure("bounded"))
        with self.assertRaises(VenueError) as raised:
            BybitTestnetVenue(client).positions()
        self.assertEqual(raised.exception.category, VenueErrorCategory.RATE_LIMIT)
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(
            len([call for call in client.calls if call[0] == "get_positions"]),
            1,
        )

    def test_repeated_cursor_fails_closed(self) -> None:
        client = FakeBybitClient()
        client.queue(
            "get_positions",
            response([], cursor="same"),
            response([], cursor="same"),
        )
        with self.assertRaises(VenueError) as raised:
            BybitTestnetVenue(client).positions()
        self.assertEqual(raised.exception.category, VenueErrorCategory.PROTOCOL)

    def test_hedge_mode_position_fails_closed(self) -> None:
        item = position_item()
        item["positionIdx"] = 1
        client = FakeBybitClient()
        client.queue("get_positions", response([item]))
        with self.assertRaises(VenueError) as raised:
            BybitTestnetVenue(client).positions()
        self.assertEqual(raised.exception.category, VenueErrorCategory.PROTOCOL)

    def test_unsafe_provider_symbol_fails_closed(self) -> None:
        item = position_item(symbol="../../private")
        client = FakeBybitClient()
        client.queue("get_positions", response([item]))
        with self.assertRaises(VenueError) as raised:
            BybitTestnetVenue(client).positions()
        self.assertEqual(raised.exception.category, VenueErrorCategory.PROTOCOL)

    def test_execution_quantity_must_match_order_summary(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        venue.submit(make_testnet_intent())
        item = order_item(status="Filled")
        item["cumExecQty"] = "0.002"
        client.queue("get_open_orders", response([item]))
        client.queue("get_executions", response([execution_item()]))
        with self.assertRaises(VenueError) as raised:
            venue.poll("ORDER-1")
        self.assertEqual(raised.exception.category, VenueErrorCategory.PROTOCOL)

    def test_unsupported_execution_type_fails_closed(self) -> None:
        client = FakeBybitClient()
        venue = BybitTestnetVenue(client)
        venue.submit(make_testnet_intent())
        client.queue("get_open_orders", response([order_item(status="Filled")]))
        execution = execution_item()
        execution["execType"] = "AdlTrade"
        client.queue("get_executions", response([execution]))
        with self.assertRaises(VenueError) as raised:
            venue.poll("ORDER-1")
        self.assertEqual(raised.exception.category, VenueErrorCategory.PROTOCOL)

    def test_missing_return_code_fails_closed(self) -> None:
        malformed = response()
        del malformed["retCode"]
        client = FakeBybitClient()
        client.queue("get_positions", malformed)
        with self.assertRaises(VenueError) as raised:
            BybitTestnetVenue(client).positions()
        self.assertEqual(raised.exception.category, VenueErrorCategory.PROTOCOL)

    def test_full_engine_receipt_records_testnet_boundary(self) -> None:
        client = FakeBybitClient()
        client.queue(
            "get_positions",
            response(),
            response([position_item()]),
        )
        client.queue(
            "get_open_orders", response(), response([order_item(status="Filled")])
        )
        client.queue("get_order_history", response())
        client.queue("get_executions", response([execution_item()]))
        venue = ConformingVenue(BybitTestnetVenue(client))
        receipt = SafeExecutionEngine(
            venue,
            expected_positions={},
            receipt_store=self.store,
        ).execute(make_testnet_intent(), scenario="bybit-testnet-contract")
        payload = receipt.to_dict()
        self.assertEqual(receipt.outcome, ReceiptOutcome.FILLED)
        self.assertEqual(payload["mode"], "testnet")
        self.assertEqual(payload["provider"], "bybit")
        self.assertEqual(payload["environment"], "testnet")
        self.assertTrue(payload["network_used"])
        self.assertTrue(payload["credentials_required"])
        self.assertFalse(payload["live_trading_permitted"])

    def test_validation_block_records_zero_network_use(self) -> None:
        venue = ConformingVenue(BybitTestnetVenue(FakeBybitClient()))
        receipt = SafeExecutionEngine(
            venue,
            expected_positions={},
            receipt_store=self.store,
        ).execute(
            make_testnet_intent(quantity="0"),
            scenario="validation-block",
        )
        self.assertEqual(receipt.outcome, ReceiptOutcome.VALIDATION_BLOCKED)
        self.assertFalse(receipt.network_used)
