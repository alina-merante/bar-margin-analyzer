from __future__ import annotations

from typing import Any

from app.services.cash_closure_parser import ClosureExtraction

AUTO_SAVE = "AUTO_SAVE"
SAVE_FOR_REVIEW = "SAVE_FOR_REVIEW"
REJECT = "REJECT"

_CORE_FIELDS = ("date", "closure_number", "total_amount")
_EVIDENCE_FIELDS = (
    "date",
    "closure_number",
    "total_amount",
    "cash_amount",
    "card_amount",
    "receipts_count",
)


def _result(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, str):
        return ClosureExtraction(value).to_result()
    return value


def classify_closure(value: str | dict[str, Any]) -> str:
    """Classify extraction output without inferring values from arithmetic."""
    extracted = _result(value)
    diagnostics = extracted.get("diagnostics") or {}
    fields = diagnostics.get("fields") or {}
    anomalies = diagnostics.get("anomalies") or []

    evidence_count = sum(
        1
        for name in _EVIDENCE_FIELDS
        if extracted.get(name) is not None
        or (fields.get(name) or {}).get("status") in {"ok", "ambiguous", "conflict", "malformed"}
    )
    if evidence_count < 2:
        return REJECT

    core_values_present = all(extracted.get(name) is not None for name in _CORE_FIELDS)
    core_fields_resolved = all(
        (fields.get(name) or {}).get("status") == "ok"
        for name in _CORE_FIELDS
    )
    total_is_explicit = diagnostics.get("total_label") == "explicit"
    no_arithmetic_resolution = all(
        (fields.get(name) or {}).get("provenance") != "arithmetic"
        for name in _CORE_FIELDS
    )

    if (
        core_values_present
        and core_fields_resolved
        and total_is_explicit
        and no_arithmetic_resolution
        and not anomalies
    ):
        return AUTO_SAVE

    return SAVE_FOR_REVIEW
