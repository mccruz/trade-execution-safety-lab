from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy

from trade_execution_safety_lab.connectors.bybit_testnet import (
    BYBIT_TESTNET_ENDPOINT,
)


def response(items: list[dict[str, object]] | None = None, *, cursor: str = ""):
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "list": list(items or []),
            "nextPageCursor": cursor,
        },
    }


def instrument_response():
    return response(
        [
            {
                "symbol": "BTCUSDT",
                "priceFilter": {"tickSize": "0.10"},
                "lotSizeFilter": {
                    "qtyStep": "0.001",
                    "minOrderQty": "0.001",
                    "minNotionalValue": "5",
                },
            }
        ]
    )


def order_item(
    *,
    status: str = "New",
    quantity: str = "0.001",
    price: str = "50000.00",
    order_id: str = "ORDER-1",
    client_order_id: str = "TESTNET-ORDER-1",
) -> dict[str, object]:
    return {
        "orderId": order_id,
        "orderLinkId": client_order_id,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "orderType": "Limit",
        "qty": quantity,
        "price": price,
        "avgPrice": price if status == "Filled" else "",
        "cumExecQty": quantity if status == "Filled" else "0",
        "leavesQty": "0" if status == "Filled" else quantity,
        "orderStatus": status,
        "positionIdx": 0,
    }


def execution_item(
    *,
    quantity: str = "0.001",
    price: str = "50000.00",
    fee: str = "0.01",
    order_id: str = "ORDER-1",
) -> dict[str, object]:
    return {
        "execType": "Trade",
        "execId": "EXEC-1",
        "orderId": order_id,
        "execQty": quantity,
        "execPrice": price,
        "execFee": fee,
        "execTime": "1000",
    }


def position_item(
    *,
    side: str = "Buy",
    size: str = "0.001",
    symbol: str = "BTCUSDT",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "side": side,
        "size": size,
        "avgPrice": "50000.00",
        "seq": "1001",
        "positionIdx": 0,
    }


class FakeBybitClient:
    def __init__(self, *, endpoint: str = BYBIT_TESTNET_ENDPOINT) -> None:
        self.endpoint = endpoint
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._queued: dict[str, list[object]] = defaultdict(list)

    def queue(self, method: str, *results: object) -> None:
        self._queued[method].extend(results)

    def _result(self, method: str, kwargs: dict[str, object]) -> Mapping[str, object]:
        self.calls.append((method, dict(kwargs)))
        if self._queued[method]:
            selected = self._queued[method].pop(0)
            if isinstance(selected, Exception):
                raise selected
            return deepcopy(selected)
        defaults: dict[str, Mapping[str, object]] = {
            "place_order": {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "orderId": "ORDER-1",
                    "orderLinkId": kwargs.get("orderLinkId", ""),
                },
            },
            "cancel_order": {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "orderId": kwargs.get("orderId", ""),
                    "orderLinkId": "",
                },
            },
            "get_open_orders": response(),
            "get_order_history": response(),
            "get_executions": response(),
            "get_positions": response(),
            "get_instruments_info": instrument_response(),
        }
        return deepcopy(defaults[method])

    def place_order(self, **kwargs: object) -> Mapping[str, object]:
        return self._result("place_order", kwargs)

    def cancel_order(self, **kwargs: object) -> Mapping[str, object]:
        return self._result("cancel_order", kwargs)

    def get_open_orders(self, **kwargs: object) -> Mapping[str, object]:
        return self._result("get_open_orders", kwargs)

    def get_order_history(self, **kwargs: object) -> Mapping[str, object]:
        return self._result("get_order_history", kwargs)

    def get_executions(self, **kwargs: object) -> Mapping[str, object]:
        return self._result("get_executions", kwargs)

    def get_positions(self, **kwargs: object) -> Mapping[str, object]:
        return self._result("get_positions", kwargs)

    def get_instruments_info(self, **kwargs: object) -> Mapping[str, object]:
        return self._result("get_instruments_info", kwargs)
