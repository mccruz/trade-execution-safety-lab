"""Canonical, checksummed, atomic execution-receipt storage."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from .models import ExecutionReceipt


OUTPUT_SENTINEL = ".trade-execution-safety-lab-output"
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def receipt_digest(payload_without_id: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        canonical_json(payload_without_id).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def finalize_receipt(draft: ExecutionReceipt) -> ExecutionReceipt:
    if draft.receipt_id:
        raise ValueError("draft receipt must not already have a receipt_id")
    receipt_id = receipt_digest(draft.to_dict(include_receipt_id=False))
    return replace(draft, receipt_id=receipt_id)


def verify_receipt_payload(payload: dict[str, Any]) -> bool:
    receipt_id = payload.get("receipt_id")
    if not isinstance(receipt_id, str):
        return False
    unsigned = dict(payload)
    unsigned.pop("receipt_id", None)
    return receipt_id == receipt_digest(unsigned)


def _validate_output_path(path: Path) -> Path:
    if path.exists() and path.is_symlink():
        raise ValueError("output directory cannot be a symbolic link")
    resolved = path.expanduser().resolve(strict=False)
    broad_targets = {
        Path(resolved.anchor),
        Path.home().resolve(),
        Path.cwd().resolve(),
    }
    if resolved in broad_targets:
        raise ValueError("refusing to use a broad directory as demo output")
    return resolved


def prepare_output_directory(path: str | Path, *, reset: bool) -> Path:
    resolved = _validate_output_path(Path(path))
    if resolved.exists():
        entries = list(resolved.iterdir())
        marker = resolved / OUTPUT_SENTINEL
        if reset:
            if entries and not marker.is_file():
                raise ValueError(
                    "refusing to reset a non-empty directory without the lab sentinel"
                )
            if marker.is_file():
                shutil.rmtree(resolved)
        elif entries:
            raise FileExistsError(
                "output directory is not empty; use --reset only for lab-owned output"
            )

    resolved.mkdir(parents=True, mode=0o700, exist_ok=True)
    marker = resolved / OUTPUT_SENTINEL
    marker.write_text("trade-execution-safety-lab:v1\n", encoding="utf-8")
    marker.chmod(0o600)
    return resolved


class AtomicReceiptStore:
    def __init__(self, root: str | Path) -> None:
        self.root = _validate_output_path(Path(root))
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        marker = self.root.parent / OUTPUT_SENTINEL
        if not marker.is_file():
            raise ValueError("receipt store must be inside a prepared lab output directory")

    def write(self, receipt: ExecutionReceipt) -> Path:
        if not _SAFE_IDENTIFIER.fullmatch(receipt.intent.client_order_id):
            raise ValueError("unsafe client order identifier")
        payload = receipt.to_dict()
        if not verify_receipt_payload(payload):
            raise ValueError("receipt digest is invalid")
        target = self.root / f"{receipt.intent.client_order_id}.json"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.root,
            prefix=".receipt-",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            target.chmod(0o600)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def read_verified(self, client_order_id: str) -> dict[str, Any] | None:
        if not _SAFE_IDENTIFIER.fullmatch(client_order_id):
            raise ValueError("unsafe client order identifier")
        target = self.root / f"{client_order_id}.json"
        if not target.exists():
            return None
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not verify_receipt_payload(payload):
            raise ValueError("stored receipt failed digest verification")
        return payload


def write_json_artifact(root: Path, relative_name: str, payload: dict[str, Any]) -> Path:
    if "/" in relative_name or "\\" in relative_name or relative_name.startswith("."):
        raise ValueError("artifact name must be a simple visible filename")
    target = root / relative_name
    descriptor, temporary_name = tempfile.mkstemp(
        dir=root,
        prefix=".artifact-",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        target.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def write_text_artifact(root: Path, relative_name: str, content: str) -> Path:
    if "/" in relative_name or "\\" in relative_name or relative_name.startswith("."):
        raise ValueError("artifact name must be a simple visible filename")
    target = root / relative_name
    descriptor, temporary_name = tempfile.mkstemp(
        dir=root,
        prefix=".artifact-",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        target.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
