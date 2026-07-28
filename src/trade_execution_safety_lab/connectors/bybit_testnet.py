"""Optional Bybit Testnet adapter with no mainnet construction path."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

from ..adapters import VenueError, VenueErrorCategory
from ..models import (
    Fill,
    Instrument,
    OrderIntent,
    OrderSnapshot,
    OrderStatus,
    OrderType,
    PositionSnapshot,
    Side,
    VenueSafetyProfile,
    decimal_text,
)

BYBIT_TESTNET_ENDPOINT = "https://api-testnet.bybit.com"
BYBIT_TESTNET_API_KEY_ENV = "BYBIT_TESTNET_API_KEY"
BYBIT_TESTNET_API_SECRET_ENV = "BYBIT_TESTNET_API_SECRET"
BYBIT_TESTNET_PROFILE = VenueSafetyProfile(
    mode="testnet",
    provider="bybit",
    environment="testnet",
    network_permitted=True,
    credentials_required=True,
)

_SAFE_COIN = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")
_SAFE_SYMBOL = re.compile(r"^[A-Z][A-Z0-9-]{2,31}$")
_SAFE_PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_AUTHENTICATION_CODES = {401, 403, 10003, 10004, 10005, 10007}
_RATE_LIMIT_CODES = {429, 10006}
_STATUS_MAP = {
    "New": OrderStatus.ACCEPTED,
    "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
    "Filled": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "Rejected": OrderStatus.REJECTED,
}


class BybitHttpClient(Protocol):
    """The official SDK methods used by this adapter."""

    endpoint: str

    def place_order(self, **kwargs: object) -> Mapping[str, object]: ...

    def cancel_order(self, **kwargs: object) -> Mapping[str, object]: ...

    def get_open_orders(self, **kwargs: object) -> Mapping[str, object]: ...

    def get_order_history(self, **kwargs: object) -> Mapping[str, object]: ...

    def get_executions(self, **kwargs: object) -> Mapping[str, object]: ...

    def get_positions(self, **kwargs: object) -> Mapping[str, object]: ...

    def get_instruments_info(self, **kwargs: object) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class BybitTestnetSettings:
    """Non-secret settings for a bounded linear-testnet adapter."""

    category: str = "linear"
    settle_coin: str = "USDT"
    maximum_pages: int = 5
    request_timeout_seconds: int = 10
    receive_window_milliseconds: int = 5_000

    def __post_init__(self) -> None:
        if self.category != "linear":
            raise ValueError(
                "the reference adapter supports only linear testnet orders"
            )
        if not _SAFE_COIN.fullmatch(self.settle_coin):
            raise ValueError("settle_coin must be a safe uppercase identifier")
        if not 1 <= self.maximum_pages <= 10:
            raise ValueError("maximum_pages must be between 1 and 10")
        if not 1 <= self.request_timeout_seconds <= 30:
            raise ValueError("request_timeout_seconds must be between 1 and 30")
        if not 1_000 <= self.receive_window_milliseconds <= 10_000:
            raise ValueError(
                "receive_window_milliseconds must be between 1000 and 10000"
            )


class BybitTestnetVenue:
    """Translate official Bybit Testnet responses into provider-neutral models."""

    name = "bybit-testnet"
    safety_profile = BYBIT_TESTNET_PROFILE

    def __init__(
        self,
        client: BybitHttpClient,
        *,
        settings: BybitTestnetSettings | None = None,
    ) -> None:
        endpoint = getattr(client, "endpoint", None)
        if endpoint != BYBIT_TESTNET_ENDPOINT:
            raise ValueError("Bybit adapter requires the fixed testnet endpoint")
        self._client = client
        self.settings = settings or BybitTestnetSettings()
        self._network_used = False
        self._instrument_cache: dict[str, Instrument] = {}
        self._intent_by_order_id: dict[str, OrderIntent] = {}
        self._last_by_order_id: dict[str, OrderSnapshot] = {}
        self._local_sequence = 0

    def __repr__(self) -> str:
        return (
            "BybitTestnetVenue("
            f"endpoint={BYBIT_TESTNET_ENDPOINT!r}, "
            f"category={self.settings.category!r})"
        )

    @classmethod
    def from_environment(
        cls,
        *,
        settings: BybitTestnetSettings | None = None,
        environ: Mapping[str, str] | None = None,
        client_factory: Callable[..., BybitHttpClient] | None = None,
    ) -> BybitTestnetVenue:
        """Create the official SDK client without copying credentials into state."""

        source = os.environ if environ is None else environ
        api_key = source.get(BYBIT_TESTNET_API_KEY_ENV, "").strip()
        api_secret = source.get(BYBIT_TESTNET_API_SECRET_ENV, "").strip()
        if not api_key or not api_secret:
            raise ValueError(
                f"{BYBIT_TESTNET_API_KEY_ENV} and "
                f"{BYBIT_TESTNET_API_SECRET_ENV} must both be set"
            )

        selected = settings or BybitTestnetSettings()
        if client_factory is None:
            try:
                from pybit.unified_trading import HTTP
            except ImportError as exc:
                raise RuntimeError(
                    "Install the optional bybit-testnet dependency before "
                    "constructing the connector."
                ) from exc
            client_factory = HTTP

        try:
            client = client_factory(
                testnet=True,
                demo=False,
                api_key=api_key,
                api_secret=api_secret,
                timeout=selected.request_timeout_seconds,
                recv_window=selected.receive_window_milliseconds,
                log_requests=False,
                force_retry=False,
                max_retries=1,
                retry_codes={0},
            )
        except Exception:  # noqa: BLE001
            raise RuntimeError("Bybit Testnet client construction failed.") from None
        return cls(client, settings=selected)

    @property
    def network_used(self) -> bool:
        return self._network_used

    def instrument(self, symbol: str) -> Instrument:
        """Load current public testnet constraints for an uppercase symbol."""

        if not _SAFE_SYMBOL.fullmatch(symbol):
            raise ValueError("symbol must be a safe uppercase identifier")
        cached = self._instrument_cache.get(symbol)
        if cached is not None:
            return cached
        response = self._call(
            "instrument lookup",
            self._client.get_instruments_info,
            category=self.settings.category,
            symbol=symbol,
            limit=1,
        )
        items, _ = self._response_items(response, "instrument lookup")
        exact = [item for item in items if item.get("symbol") == symbol]
        if len(exact) != 1:
            self._protocol_failure("instrument lookup was not uniquely resolved")
        item = exact[0]
        price_filter = self._mapping(item.get("priceFilter"), "priceFilter")
        lot_filter = self._mapping(item.get("lotSizeFilter"), "lotSizeFilter")
        instrument = Instrument(
            symbol=self._text(item.get("symbol"), "symbol"),
            price_tick=self._positive_decimal(
                price_filter.get("tickSize"),
                "tickSize",
            ),
            quantity_step=self._positive_decimal(
                lot_filter.get("qtyStep"),
                "qtyStep",
            ),
            minimum_quantity=self._positive_decimal(
                lot_filter.get("minOrderQty"),
                "minOrderQty",
            ),
            minimum_notional=self._positive_decimal(
                lot_filter.get("minNotionalValue"),
                "minNotionalValue",
            ),
        )
        self._instrument_cache[symbol] = instrument
        return instrument

    def submit(self, intent: OrderIntent) -> OrderSnapshot:
        self._validate_client_order_id(intent.client_order_id)
        if self.instrument(intent.instrument.symbol) != intent.instrument:
            self._protocol_failure(
                "intent constraints do not match the current testnet instrument"
            )

        payload: dict[str, object] = {
            "category": self.settings.category,
            "symbol": intent.instrument.symbol,
            "side": "Buy" if intent.side is Side.BUY else "Sell",
            "orderType": "Limit" if intent.order_type is OrderType.LIMIT else "Market",
            "qty": decimal_text(intent.quantity),
            "orderLinkId": intent.client_order_id,
            "positionIdx": 0,
        }
        if intent.order_type is OrderType.LIMIT:
            payload["price"] = decimal_text(intent.limit_price or Decimal("0"))
            payload["timeInForce"] = "GTC"

        response = self._call(
            "order submission",
            self._client.place_order,
            **payload,
        )
        result = self._result_mapping(response, "order submission")
        venue_order_id = self._text(result.get("orderId"), "orderId")
        returned_client_id = str(result.get("orderLinkId") or intent.client_order_id)
        if returned_client_id != intent.client_order_id:
            self._protocol_failure(
                "testnet acknowledgement changed the client order id"
            )

        snapshot = OrderSnapshot(
            venue_order_id=venue_order_id,
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=OrderStatus.ACCEPTED,
            reason="testnet-order-acknowledged",
            sequence=self._next_sequence(),
        )
        self._intent_by_order_id[venue_order_id] = intent
        self._remember(snapshot)
        return snapshot

    def poll(self, venue_order_id: str) -> OrderSnapshot:
        self._validate_provider_id(venue_order_id, "venue order id")
        item = self._find_order(order_id=venue_order_id)
        if item is None:
            return self._unknown_snapshot(venue_order_id)
        snapshot = self._snapshot_from_item(item)
        self._remember(snapshot)
        return snapshot

    def cancel(self, venue_order_id: str) -> OrderSnapshot:
        self._validate_provider_id(venue_order_id, "venue order id")
        current = self._last_by_order_id.get(venue_order_id)
        if current is None:
            current = self.poll(venue_order_id)
        if current.status.terminal:
            return current

        self._call(
            "order cancellation",
            self._client.cancel_order,
            category=self.settings.category,
            symbol=current.instrument.symbol,
            orderId=venue_order_id,
        )
        observed = self.poll(venue_order_id)
        if observed.status is not OrderStatus.UNKNOWN:
            return observed
        pending = OrderSnapshot(
            venue_order_id=current.venue_order_id,
            client_order_id=current.client_order_id,
            instrument=current.instrument,
            side=current.side,
            order_type=current.order_type,
            requested_quantity=current.requested_quantity,
            status=OrderStatus.CANCEL_PENDING,
            fills=current.fills,
            reason="testnet-cancellation-acknowledged",
            sequence=self._next_sequence(),
        )
        self._remember(pending)
        return pending

    def find_by_client_order_id(
        self,
        client_order_id: str,
    ) -> OrderSnapshot | None:
        self._validate_client_order_id(client_order_id)
        item = self._find_order(client_order_id=client_order_id)
        if item is None:
            return None
        snapshot = self._snapshot_from_item(item)
        if snapshot.client_order_id != client_order_id:
            self._protocol_failure("client-order lookup returned a different order")
        self._remember(snapshot)
        return snapshot

    def positions(self) -> tuple[PositionSnapshot, ...]:
        items = self._paged_items(
            "position lookup",
            self._client.get_positions,
            category=self.settings.category,
            settleCoin=self.settings.settle_coin,
            limit=200,
        )
        positions: list[PositionSnapshot] = []
        for item in items:
            if (
                "positionIdx" in item
                and self._nonnegative_int(
                    item.get("positionIdx"),
                    "position index",
                )
                != 0
            ):
                self._protocol_failure(
                    "hedge-mode positions are outside the connector contract"
                )
            size = self._nonnegative_decimal(item.get("size"), "position size")
            if size == 0:
                continue
            side = self._text(item.get("side"), "position side")
            if side == "Buy":
                quantity = size
            elif side == "Sell":
                quantity = -size
            else:
                self._protocol_failure("position side was not recognized")
            average_text = str(item.get("avgPrice") or "")
            average_price = (
                self._positive_decimal(average_text, "average price")
                if average_text
                else None
            )
            sequence = self._nonnegative_int(item.get("seq"), "position sequence")
            positions.append(
                PositionSnapshot(
                    symbol=self._symbol(item.get("symbol"), "position symbol"),
                    quantity=quantity,
                    average_price=average_price,
                    sequence=sequence,
                )
            )
        return tuple(positions)

    def _find_order(
        self,
        *,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> Mapping[str, object] | None:
        if (order_id is None) == (client_order_id is None):
            raise ValueError("exactly one order identifier is required")
        identifier = (
            {"orderId": order_id}
            if order_id is not None
            else {"orderLinkId": client_order_id}
        )
        for operation, method in (
            ("open-order lookup", self._client.get_open_orders),
            ("order-history lookup", self._client.get_order_history),
        ):
            response = self._call(
                operation,
                method,
                category=self.settings.category,
                **identifier,
                limit=50,
            )
            items, _ = self._response_items(response, operation)
            exact = [
                item
                for item in items
                if (
                    item.get("orderId") == order_id
                    if order_id is not None
                    else item.get("orderLinkId") == client_order_id
                )
            ]
            if len(exact) > 1:
                self._protocol_failure("order lookup returned duplicate identifiers")
            if exact:
                return exact[0]
        return None

    def _snapshot_from_item(
        self,
        item: Mapping[str, object],
    ) -> OrderSnapshot:
        venue_order_id = self._text(item.get("orderId"), "orderId")
        self._validate_provider_id(venue_order_id, "venue order id")
        cached_intent = self._intent_by_order_id.get(venue_order_id)
        client_order_id = str(item.get("orderLinkId") or "")
        if not client_order_id and cached_intent is not None:
            client_order_id = cached_intent.client_order_id
        if not client_order_id:
            self._protocol_failure("order response omitted its client order identifier")
        self._validate_client_order_id(client_order_id)
        if (
            "positionIdx" in item
            and self._nonnegative_int(
                item.get("positionIdx"),
                "position index",
            )
            != 0
        ):
            self._protocol_failure(
                "hedge-mode orders are outside the connector contract"
            )

        symbol = self._symbol(item.get("symbol"), "symbol")
        instrument = (
            cached_intent.instrument
            if cached_intent is not None
            else self.instrument(symbol)
        )
        side_text = self._text(item.get("side"), "side")
        order_type_text = self._text(item.get("orderType"), "orderType")
        status_text = self._text(item.get("orderStatus"), "orderStatus")
        status = _STATUS_MAP.get(status_text, OrderStatus.UNKNOWN)
        fills = self._fills(venue_order_id)
        requested_quantity = self._positive_decimal(
            item.get("qty"),
            "order quantity",
        )
        if item.get("cumExecQty") not in {None, ""}:
            provider_filled_quantity = self._nonnegative_decimal(
                item.get("cumExecQty"),
                "cumulative execution quantity",
            )
            normalized_filled_quantity = sum(
                (fill.quantity for fill in fills),
                Decimal("0"),
            )
            if provider_filled_quantity != normalized_filled_quantity:
                self._protocol_failure(
                    "execution history disagreed with cumulative execution quantity"
                )
        if item.get("leavesQty") not in {None, ""}:
            provider_remaining_quantity = self._nonnegative_decimal(
                item.get("leavesQty"),
                "remaining quantity",
            )
            if provider_remaining_quantity != requested_quantity - sum(
                (fill.quantity for fill in fills), Decimal("0")
            ):
                self._protocol_failure(
                    "execution history disagreed with remaining order quantity"
                )
        snapshot = OrderSnapshot(
            venue_order_id=venue_order_id,
            client_order_id=client_order_id,
            instrument=instrument,
            side=self._side(side_text),
            order_type=self._order_type(order_type_text),
            requested_quantity=requested_quantity,
            status=status,
            fills=fills,
            reason=(
                "testnet-status-unmapped"
                if status is OrderStatus.UNKNOWN
                else f"testnet-{status.value}"
            ),
            sequence=self._next_sequence(),
        )
        return snapshot

    def _fills(self, venue_order_id: str) -> tuple[Fill, ...]:
        items = self._paged_items(
            "execution lookup",
            self._client.get_executions,
            category=self.settings.category,
            orderId=venue_order_id,
            limit=100,
        )
        unique: dict[str, tuple[Decimal, Decimal, Decimal, int]] = {}
        for item in items:
            if self._text(item.get("execType"), "execType") != "Trade":
                self._protocol_failure(
                    "execution type is outside the linear order contract"
                )
            if self._text(item.get("orderId"), "execution orderId") != venue_order_id:
                self._protocol_failure(
                    "execution lookup returned a different venue order id"
                )
            fill_id = self._text(item.get("execId"), "execId")
            self._validate_provider_id(fill_id, "execution id")
            values = (
                self._positive_decimal(item.get("execQty"), "execution quantity"),
                self._positive_decimal(item.get("execPrice"), "execution price"),
                self._decimal(item.get("execFee"), "execution fee"),
                self._nonnegative_int(item.get("execTime"), "execution time"),
            )
            prior = unique.get(fill_id)
            if prior is not None and prior != values:
                self._protocol_failure("duplicate execution identifiers disagreed")
            unique[fill_id] = values

        ordered = sorted(
            unique.items(),
            key=lambda item: (item[1][3], item[0]),
        )
        return tuple(
            Fill(
                fill_id=fill_id,
                quantity=values[0],
                price=values[1],
                fee=values[2],
                sequence=index,
            )
            for index, (fill_id, values) in enumerate(ordered, start=1)
        )

    def _unknown_snapshot(self, venue_order_id: str) -> OrderSnapshot:
        previous = self._last_by_order_id.get(venue_order_id)
        intent = self._intent_by_order_id.get(venue_order_id)
        if previous is None and intent is None:
            self._protocol_failure("unknown venue order id cannot be normalized")
        if previous is not None:
            return OrderSnapshot(
                venue_order_id=previous.venue_order_id,
                client_order_id=previous.client_order_id,
                instrument=previous.instrument,
                side=previous.side,
                order_type=previous.order_type,
                requested_quantity=previous.requested_quantity,
                status=OrderStatus.UNKNOWN,
                fills=previous.fills,
                reason="testnet-order-not-visible",
                sequence=self._next_sequence(),
            )
        assert intent is not None
        return OrderSnapshot(
            venue_order_id=venue_order_id,
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=OrderStatus.UNKNOWN,
            reason="testnet-order-not-visible",
            sequence=self._next_sequence(),
        )

    def _paged_items(
        self,
        operation: str,
        method: Callable[..., Mapping[str, object]],
        **parameters: object,
    ) -> tuple[Mapping[str, object], ...]:
        items: list[Mapping[str, object]] = []
        seen_cursors: set[str] = set()
        current = dict(parameters)
        for _ in range(self.settings.maximum_pages):
            response = self._call(operation, method, **current)
            page, cursor = self._response_items(response, operation)
            items.extend(page)
            if not cursor:
                return tuple(items)
            if cursor in seen_cursors:
                self._protocol_failure("provider pagination cursor repeated")
            seen_cursors.add(cursor)
            current["cursor"] = cursor
        self._protocol_failure("provider pagination exceeded the configured bound")

    def _response_items(
        self,
        response: Mapping[str, object],
        operation: str,
    ) -> tuple[tuple[Mapping[str, object], ...], str]:
        result = self._result_mapping(response, operation)
        raw_items = result.get("list")
        if not isinstance(raw_items, list):
            self._protocol_failure(f"{operation} response omitted its item list")
        items: list[Mapping[str, object]] = []
        for item in raw_items:
            if not isinstance(item, Mapping):
                self._protocol_failure(f"{operation} returned a malformed item")
            items.append(item)
        cursor = str(result.get("nextPageCursor") or "")
        return tuple(items), cursor

    def _result_mapping(
        self,
        response: Mapping[str, object],
        operation: str,
    ) -> Mapping[str, object]:
        if not isinstance(response, Mapping):
            self._protocol_failure(f"{operation} returned a malformed response")
        if "retCode" not in response:
            self._protocol_failure(f"{operation} response omitted its return code")
        ret_code = response["retCode"]
        if ret_code not in {0, "0"}:
            self._response_code_failure(ret_code, operation)
        return self._mapping(response.get("result"), f"{operation} result")

    def _call(
        self,
        operation: str,
        method: Callable[..., Mapping[str, object]],
        **parameters: object,
    ) -> Mapping[str, object]:
        self._network_used = True
        try:
            response = method(**parameters)
        except VenueError:
            raise
        # Official SDK exceptions do not share one stable public base class.
        except Exception as exc:  # noqa: BLE001
            self._exception_failure(exc, operation)
        if not isinstance(response, Mapping):
            self._protocol_failure(f"{operation} returned a malformed response")
        return response

    def _exception_failure(self, exc: Exception, operation: str) -> None:
        raw_status = getattr(exc, "status_code", None)
        try:
            status = int(raw_status)
        except (TypeError, ValueError):
            status = None
        name = type(exc).__name__.lower()
        if status in _AUTHENTICATION_CODES:
            category = VenueErrorCategory.AUTHENTICATION
        elif status in _RATE_LIMIT_CODES:
            category = VenueErrorCategory.RATE_LIMIT
        elif any(
            marker in name
            for marker in ("timeout", "connection", "ssl", "failedrequest")
        ):
            category = VenueErrorCategory.TRANSIENT
        elif isinstance(exc, (TypeError, ValueError, KeyError)):
            category = VenueErrorCategory.PROTOCOL
        else:
            category = VenueErrorCategory.UNKNOWN
        raise VenueError(
            f"Bybit Testnet {operation} failed.",
            category=category,
            retryable=category
            in {VenueErrorCategory.TRANSIENT, VenueErrorCategory.RATE_LIMIT},
        ) from None

    def _response_code_failure(self, code: object, operation: str) -> None:
        try:
            numeric = int(code)
        except (TypeError, ValueError):
            numeric = None
        if numeric in _AUTHENTICATION_CODES:
            category = VenueErrorCategory.AUTHENTICATION
        elif numeric in _RATE_LIMIT_CODES:
            category = VenueErrorCategory.RATE_LIMIT
        else:
            category = VenueErrorCategory.PROTOCOL
        raise VenueError(
            f"Bybit Testnet {operation} was rejected.",
            category=category,
            retryable=category is VenueErrorCategory.RATE_LIMIT,
        )

    @staticmethod
    def _mapping(value: object, field: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise VenueError(
                f"Bybit Testnet response field {field} was malformed.",
                category=VenueErrorCategory.PROTOCOL,
                retryable=False,
            )
        return value

    @staticmethod
    def _text(value: object, field: str) -> str:
        text = str(value or "")
        if not text:
            raise VenueError(
                f"Bybit Testnet response field {field} was empty.",
                category=VenueErrorCategory.PROTOCOL,
                retryable=False,
            )
        return text

    @staticmethod
    def _symbol(value: object, field: str) -> str:
        text = BybitTestnetVenue._text(value, field)
        if not _SAFE_SYMBOL.fullmatch(text):
            BybitTestnetVenue._protocol_failure(
                f"{field} was not a safe uppercase identifier"
            )
        return text

    @staticmethod
    def _positive_decimal(value: object, field: str) -> Decimal:
        parsed = BybitTestnetVenue._decimal(value, field)
        if parsed <= 0:
            BybitTestnetVenue._protocol_failure(f"{field} must be positive")
        return parsed

    @staticmethod
    def _nonnegative_decimal(value: object, field: str) -> Decimal:
        parsed = BybitTestnetVenue._decimal(value, field)
        if parsed < 0:
            BybitTestnetVenue._protocol_failure(f"{field} cannot be negative")
        return parsed

    @staticmethod
    def _decimal(value: object, field: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            BybitTestnetVenue._protocol_failure(f"{field} was not decimal-safe")
        if not parsed.is_finite():
            BybitTestnetVenue._protocol_failure(f"{field} must be finite")
        return parsed

    @staticmethod
    def _nonnegative_int(value: object, field: str) -> int:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            BybitTestnetVenue._protocol_failure(f"{field} was not an integer")
        if parsed < 0:
            BybitTestnetVenue._protocol_failure(f"{field} cannot be negative")
        return parsed

    @staticmethod
    def _side(value: str) -> Side:
        if value == "Buy":
            return Side.BUY
        if value == "Sell":
            return Side.SELL
        BybitTestnetVenue._protocol_failure("order side was not recognized")

    @staticmethod
    def _order_type(value: str) -> OrderType:
        if value == "Limit":
            return OrderType.LIMIT
        if value == "Market":
            return OrderType.MARKET
        BybitTestnetVenue._protocol_failure("order type was not recognized")

    def _next_sequence(self) -> int:
        self._local_sequence += 1
        return self._local_sequence

    def _remember(self, snapshot: OrderSnapshot) -> None:
        self._last_by_order_id[snapshot.venue_order_id] = snapshot

    @staticmethod
    def _validate_client_order_id(value: str) -> None:
        if not _SAFE_PROVIDER_ID.fullmatch(value) or len(value) > 36:
            BybitTestnetVenue._protocol_failure(
                "client order identifiers must be safe and no longer than 36 characters"
            )

    @staticmethod
    def _validate_provider_id(value: str, field: str) -> None:
        if not _SAFE_PROVIDER_ID.fullmatch(value):
            BybitTestnetVenue._protocol_failure(f"{field} was not a safe identifier")

    @staticmethod
    def _protocol_failure(message: str) -> None:
        raise VenueError(
            f"Bybit Testnet protocol failure: {message}.",
            category=VenueErrorCategory.PROTOCOL,
            retryable=False,
        )
