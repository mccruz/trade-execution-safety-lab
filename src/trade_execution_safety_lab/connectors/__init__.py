"""Optional, isolated execution-venue connectors."""

from .bybit_testnet import (
    BYBIT_TESTNET_PROFILE,
    BybitTestnetSettings,
    BybitTestnetVenue,
)


def connector_catalog() -> tuple[dict[str, object], ...]:
    """Return non-secret connector capabilities without loading an SDK."""

    return (
        {
            "name": "offline-simulator",
            "availability": "built-in default",
            "network_permitted": False,
            "credentials_required": False,
            "live_trading_permitted": False,
            "detail": "deterministic synthetic failure and recovery scenarios",
        },
        {
            "name": "bybit-testnet",
            "availability": "optional reference adapter",
            "network_permitted": True,
            "credentials_required": True,
            "live_trading_permitted": False,
            "detail": (
                "official pybit SDK, fixed Testnet endpoint, linear one-way mode"
            ),
        },
    )


__all__ = [
    "BYBIT_TESTNET_PROFILE",
    "BybitTestnetSettings",
    "BybitTestnetVenue",
    "connector_catalog",
]
