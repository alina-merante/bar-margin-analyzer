from __future__ import annotations

from typing import Any

from app.services.cash_closure_parser import ClosureExtraction

AUTO_SAVE = "AUTO_SAVE"
SAVE_FOR_REVIEW = "SAVE_FOR_REVIEW"
REJECT = "REJECT"

_EVIDENCE_FIELDS = (
    "date",
    "closure_number",
    "total_amount",
    "cash_amount",
    "card_amount",
    "receipts_count",
    "receipts_total",
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

    def has_evidence(name: str) -> bool:
        return extracted.get(name) is not None or (fields.get(name) or {}).get(
            "status"
        ) in {"ok", "ambiguous", "conflict", "malformed"}

    evidence_count = sum(has_evidence(name) for name in _EVIDENCE_FIELDS)
    closure_evidence = (
        has_evidence("closure_number")
        or (has_evidence("total_amount") and diagnostics.get("total_label") == "explicit")
        or all(has_evidence(name) for name in ("date", "receipts_count", "receipts_total"))
    )
    if evidence_count < 2 or not closure_evidence:
        return REJECT

    return SAVE_FOR_REVIEW
