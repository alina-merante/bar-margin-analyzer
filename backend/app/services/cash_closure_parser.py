"""Interpretazione del testo OCR di una chiusura di cassa.

Il modulo lavora solo sul testo: non esegue OCR e non accede al database.
Per ogni campo raccoglie tutti i candidati (con etichetta, riga e livello di
affidabilità dell'etichetta), non il primo valore trovato. I valori non
riconosciuti restano ``None``: non vengono mai convertiti in zero né dedotti.

I "livelli" (tier) indicano la forza dell'etichetta: 1 = esplicita, 2 = debole
o generica. Un livello 2 viene usato solo se manca il livello 1. Non sono
percentuali né probabilità che il valore sia corretto.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import NamedTuple

REQUIRED_FIELDS = ("date", "closure_number", "total_amount")
FIELD_NAMES = (
    "date",
    "closure_number",
    "total_amount",
    "cash_amount",
    "card_amount",
    "receipts_count",
)

STRONG_TIER = 1
WEAK_TIER = 2


class LabelSpec(NamedTuple):
    name: str
    tier: int
    pattern: re.Pattern


def _c(pattern: str) -> re.Pattern:
    return re.compile(pattern)


# Importo italiano rigoroso: 1.234,56 oppure 1234,56. Nulla di diverso è valido.
_AMOUNT = r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}"
_CURRENCY = r"(?:€|EURO?)?"
_AMOUNT_AFTER = re.compile(rf"[\s:.]*{_CURRENCY}\s*({_AMOUNT})(?!\w|,\d)")
_AMOUNT_LINE = re.compile(rf"[\s:.]*{_CURRENCY}\s*({_AMOUNT})\s*{_CURRENCY}\s*")
_TOKEN_AFTER = re.compile(rf"[\s:.]*{_CURRENCY}\s*(\d[\w.,]*)(\s\d{{3}},\d{{2}})?")
_FILLER_ONLY = re.compile(rf"[\s:.€]*{_CURRENCY}[\s:.]*")
_THOUSAND_PART = re.compile(r"\d{1,3}")

_TOTAL_EXCLUDE = _c(
    r"GRAN\s*TOT|PROGRESS|CUMUL|ANNULL|\bRESO\b|\bRESI\b|STORN|SCONT[OI]\b|RESTO|"
    r"\bIVA\b|IMPOSTA|IMPONIBILE|PARZIAL|SUBTOT|NON\s+RISCOSS"
)
_CASH_EXCLUDE = _c(
    r"RESTO|FONDO|PRELIEV|VERSAM|IN\s+CASSA|SCONT[OI]\b|CREDITO|NON\s+RISCOSS|"
    r"ANNULL|STORN|\bRESO\b"
)
_CARD_EXCLUDE = _c(
    r"FEDELT|REGALO|GIFT|RESTO|SCONT[OI]\b|CREDITO\s+RESIDUO|ANNULL|STORN|\bRESO\b"
)
_OTHER_EXCLUDE = _c(r"RESTO|ANNULL|STORN|\bRESO\b|SCONT[OI]\b")

TOTAL_LABELS = (
    LabelSpec("ammontare_giorno", STRONG_TIER, _c(r"AMMONTARE\s+GIORN(?:O|ATA|ALIERO)")),
    LabelSpec(
        "corrispettivi",
        STRONG_TIER,
        _c(r"CORRISP(?:ETTIV[IO])?(?![A-Z])[.,]?(?:\s+(?:GIORNALIER[OI]|GIORNATA))?"),
    ),
    LabelSpec(
        "totale_giornaliero",
        STRONG_TIER,
        _c(
            r"TOT(?:ALE|\.)\s+(?:GIORNALIER[OI]|GIORNATA|INCASS[OI]|CORRISPETTIVI|"
            r"VENDITE|COMPLESSIVO)"
        ),
    ),
    LabelSpec(
        "incasso_giornaliero",
        STRONG_TIER,
        _c(r"INCASS[OI]\s+(?:GIORNALIER[OI]|TOTAL[EI]|GIORNATA|DEL\s+GIORNO)"),
    ),
    LabelSpec("vendite_giornaliere", STRONG_TIER, _c(r"VENDITE\s+GIORNALIERE")),
    # "TOTALE" da solo è accettato solo se manca ogni etichetta esplicita.
    LabelSpec("totale_generico", WEAK_TIER, _c(r"(?<![A-Z])TOT(?:ALE(?![A-Z])|\.)")),
)

CASH_LABELS = (
    LabelSpec("contanti", STRONG_TIER, _c(r"(?<![A-Z])(?:CONTANTI|CONTANTE|CASH)(?![A-Z])")),
    # Etichetta storica già supportata: "AMMONTARE <importo>" senza "GIORNO".
    LabelSpec("ammontare", WEAK_TIER, _c(r"(?<![A-Z])AMMONTARE(?![A-Z])")),
)

CARD_LABELS = (
    LabelSpec(
        "pagamenti_elettronici",
        STRONG_TIER,
        _c(r"(?:PAGAM(?:ENT[IO])?[.,]?\s*)?ELETTRONIC[IO](?![A-Z])"),
    ),
    # Singoli strumenti: se compaiono con importi diversi non vengono sommati.
    LabelSpec(
        "strumenti_elettronici",
        WEAK_TIER,
        _c(
            r"(?<![A-Z])(?:CARTE\s+E\s+BANCOMAT|BANCOMAT|POS|CARDS?|"
            r"CARTE?(?:\s+DI\s+(?:CREDITO|DEBITO))?)(?![A-Z])"
        ),
    ),
)

# Modalità aggiuntive: solo rilevate per spiegare il totale, mai contabilizzate.
OTHER_PAYMENT_LABELS = (
    ("buoni_pasto", _c(r"(?:BUON[OI]\s+PASTO|TICKET(?:\s+RESTAURANT)?)(?![A-Z])")),
    ("satispay", _c(r"SATISPAY")),
    ("assegni", _c(r"(?<![A-Z])ASSEGN[OI](?![A-Z])")),
    ("bonifici", _c(r"(?<![A-Z])BONIFIC[OI](?![A-Z])")),
    ("non_riscosso", _c(r"NON\s+RISCOSS[OI]")),
    ("altri_pagamenti", _c(r"ALTRI\s+PAGAMENTI")),
)

_N_MARK = r"(?:N(?:UM(?:ERO)?)?|NR)[.°º]?(?![A-Z])"
_NUM_TOKEN = r"([A-Z0-9]{1,12})(?![A-Z0-9])"
_NUMBER_SEP = r"\s*[:#\-]?\s*"
_NUMBER_SEP_SAME_LINE = r"[ \t]*[:#\-]?[ \t]*"
CLOSURE_LABELS = (
    LabelSpec(
        "numero_chiusura",
        STRONG_TIER,
        _c(
            rf"(?<![A-Z]){_N_MARK}\s*(?:DI\s+)?(?:CHIUSURA|AZZERAMENTO|"
            rf"(?:RAPPORTO|REPORT)\s*Z){_NUMBER_SEP}{_NUM_TOKEN}"
        ),
    ),
    LabelSpec(
        "chiusura_n",
        STRONG_TIER,
        _c(
            rf"CHIUSURA(?:\s+(?:GIORNALIERA|FISCALE|DI\s+CASSA|CASSA))?\s*{_N_MARK}"
            rf"{_NUMBER_SEP}{_NUM_TOKEN}"
        ),
    ),
    LabelSpec(
        "rapporto_z",
        WEAK_TIER,
        _c(
            r"(?:(?:RAPPORTO|REPORT)\s*Z|Z[\s\-]*(?:REPORT|RAPPORTO)|AZZERAMENT[OI])"
            rf"(?:[ \t]*{_N_MARK})?{_NUMBER_SEP_SAME_LINE}{_NUM_TOKEN}"
        ),
    ),
    LabelSpec(
        "z_numero",
        WEAK_TIER,
        # Una "Z" isolata vale come etichetta solo se seguita da un marcatore di numero.
        _c(rf"(?<![A-Z0-9])Z[ \t]*{_N_MARK}{_NUMBER_SEP_SAME_LINE}{_NUM_TOKEN}"),
    ),
    LabelSpec(
        "chiusura",
        WEAK_TIER,
        _c(
            rf"CHIUSURA(?:[ \t]+(?:GIORNALIERA|FISCALE))?{_NUMBER_SEP_SAME_LINE}{_NUM_TOKEN}"
        ),
    ),
)
_NUMBER_FOLLOWED_BY_DATE_OR_TIME = re.compile(r"[/.:,\-]\d")

_RECEIPT_COUNT = r"[\s:.]*(\d{1,6})(?!\w|[,.]\d)"
RECEIPT_LABELS = (
    LabelSpec(
        "documenti_vendita",
        STRONG_TIER,
        _c(
            r"DOCUM(?:ENTI|ENTO)?\.?\s+(?:COMMERCIAL[IE]|DI\s+VENDITA|EMESS[IO])"
            + _RECEIPT_COUNT
        ),
    ),
    LabelSpec(
        "scontrini",
        STRONG_TIER,
        _c(r"SCONTRINI(?:[ \t]+EMESSI)?[ \t:.]*(\d{1,6})(?!\w|[,.]\d)"),
    ),
)

_DATE_RE = re.compile(
    r"(?P<label>(?:DEL\s+GIORNO|DATA(?:\s+(?:CHIUSURA|FISCALE|DOCUMENTO))?|GIORNO|"
    r"CHIUSURA\s+DEL)\s*[:.]?)?\s*(?<!\d)(?:"
    r"(?P<d1>\d{2})[-/.](?P<m1>\d{2})[-/.](?P<y1>\d{4})|"
    r"(?P<d2>\d{2})[-/](?P<m2>\d{2})[-/](?P<y2>\d{2})|"
    r"(?P<y3>\d{4})-(?P<m3>\d{2})-(?P<d3>\d{2}))(?!\d)"
)


@dataclass(frozen=True)
class Candidate:
    value: object
    label: str
    tier: int
    line: int
    evidence: str
    proximity: str = "same_line"


@dataclass
class FieldReading:
    """Tutto ciò che una singola lettura OCR ha trovato per un campo."""

    candidates: list[Candidate] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)

    def add(self, candidate: Candidate) -> None:
        key = (candidate.value, candidate.tier, candidate.line)
        if all((c.value, c.tier, c.line) != key for c in self.candidates):
            self.candidates.append(candidate)

    def best_tier_values(self) -> tuple[int | None, list]:
        if not self.candidates:
            return None, []
        tier = min(c.tier for c in self.candidates)
        values: list = []
        for candidate in self.candidates:
            if candidate.tier == tier and candidate.value not in values:
                values.append(candidate.value)
        return tier, values

    def all_values(self) -> list:
        values: list = []
        for candidate in self.candidates:
            if candidate.value not in values:
                values.append(candidate.value)
        return values


@dataclass
class ParsedText:
    fields: dict[str, FieldReading]
    other_payments: list[tuple[str, Decimal]]


def parse_amount(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def _is_malformed_amount(token_match: re.Match) -> bool:
    token, rest = token_match.group(1), token_match.group(2)
    if re.search(r"[.,A-Z]", token):
        return True
    return bool(rest) and bool(_THOUSAND_PART.fullmatch(token))


def _next_nonempty_line(lines: list[str], index: int) -> int | None:
    for position in range(index + 1, len(lines)):
        if lines[position].strip():
            return position
    return None


def _scan_amounts(lines: list[str], specs, exclude: re.Pattern) -> FieldReading:
    reading = FieldReading()
    for index, line in enumerate(lines):
        if exclude.search(line):
            continue
        for spec in specs:
            for match in spec.pattern.finditer(line):
                _collect_amount(reading, lines, index, match.end(), spec)
    return reading


def _collect_amount(reading: FieldReading, lines: list[str], index: int, end: int, spec) -> None:
    line = lines[index]
    amount = _AMOUNT_AFTER.match(line, end)
    if amount:
        reading.add(
            Candidate(parse_amount(amount.group(1)), spec.name, spec.tier, index, line.strip())
        )
        return
    token = _TOKEN_AFTER.match(line, end)
    if token and _is_malformed_amount(token):
        reading.malformed.append(token.group(1))
        return
    if not _FILLER_ONLY.fullmatch(line, end):
        return
    # Etichetta senza importo sulla stessa riga: si guarda solo la riga successiva.
    following = _next_nonempty_line(lines, index)
    if following is None:
        return
    next_amount = _AMOUNT_LINE.fullmatch(lines[following])
    if next_amount:
        reading.add(
            Candidate(
                parse_amount(next_amount.group(1)),
                spec.name,
                spec.tier,
                following,
                f"{line.strip()} / {lines[following].strip()}",
                "next_line",
            )
        )


def _scan_other_payments(lines: list[str]) -> list[tuple[str, Decimal]]:
    found: dict[str, list[Decimal]] = {}
    for line in lines:
        if _OTHER_EXCLUDE.search(line):
            continue
        for name, pattern in OTHER_PAYMENT_LABELS:
            for match in pattern.finditer(line):
                amount = _AMOUNT_AFTER.match(line, match.end())
                if amount:
                    value = parse_amount(amount.group(1))
                    if value not in found.setdefault(name, []):
                        found[name].append(value)
    # Una modalità con importi discordanti non è utilizzabile per spiegare il totale.
    return [(name, values[0]) for name, values in found.items() if len(values) == 1]


def _scan_dates(text: str, reading: FieldReading) -> None:
    for match in _DATE_RE.finditer(text):
        if match.group("d1"):
            day, month, year = int(match.group("d1")), int(match.group("m1")), int(match.group("y1"))
        elif match.group("d2"):
            day, month, year = int(match.group("d2")), int(match.group("m2")), int(match.group("y2"))
            year += 2000
        else:
            day, month, year = int(match.group("d3")), int(match.group("m3")), int(match.group("y3"))
        raw = match.group(0).strip()
        try:
            value = dt.date(year, month, day)
        except ValueError:
            reading.malformed.append(raw)
            continue
        labeled = match.group("label") is not None
        line = text.count("\n", 0, match.start())
        reading.add(
            Candidate(
                value,
                "data_etichettata" if labeled else "data_senza_etichetta",
                STRONG_TIER if labeled else WEAK_TIER,
                line,
                raw,
            )
        )


def _scan_closure_number(text: str, reading: FieldReading) -> None:
    for spec in CLOSURE_LABELS:
        for match in spec.pattern.finditer(text):
            token = match.group(1)
            line = text.count("\n", 0, match.start())
            if token.isdigit():
                if _NUMBER_FOLLOWED_BY_DATE_OR_TIME.match(text, match.end(1)):
                    continue
                reading.add(Candidate(token, spec.name, spec.tier, line, match.group(0).strip()))
            elif re.search(r"\d", token) and re.search(r"[A-Z]", token):
                reading.malformed.append(token)


def _scan_receipts(text: str, reading: FieldReading) -> None:
    for spec in RECEIPT_LABELS:
        for match in spec.pattern.finditer(text):
            line = text.count("\n", 0, match.start())
            reading.add(
                Candidate(int(match.group(1)), spec.name, spec.tier, line, match.group(0).strip())
            )


def parse_text(text: str) -> ParsedText:
    normalized = text.replace("\u00a0", " ").upper()
    lines = normalized.splitlines()

    fields = {name: FieldReading() for name in FIELD_NAMES}
    _scan_dates(normalized, fields["date"])
    _scan_closure_number(normalized, fields["closure_number"])
    fields["total_amount"] = _scan_amounts(lines, TOTAL_LABELS, _TOTAL_EXCLUDE)
    fields["cash_amount"] = _scan_amounts(lines, CASH_LABELS, _CASH_EXCLUDE)
    fields["card_amount"] = _scan_amounts(lines, CARD_LABELS, _CARD_EXCLUDE)
    _scan_receipts(normalized, fields["receipts_count"])
    return ParsedText(fields=fields, other_payments=_scan_other_payments(lines))


@dataclass
class FieldResolution:
    status: str = "missing"  # ok | ambiguous | conflict | malformed | missing
    values: list = field(default_factory=list)
    provenance: str = ""  # first_read | second_read | confirmed | arithmetic
    tier: int | None = None
    seen: list = field(default_factory=list)
    # Valori del solo livello di etichetta migliore: i dettagli di livello inferiore
    # (es. righe POS accanto a un aggregato) non sono candidati concorrenti.
    competing: list = field(default_factory=list)

    @property
    def value(self):
        return self.values[0] if self.status == "ok" else None


def _union(first: list, second: list) -> list:
    return first + [value for value in second if value not in first]


def _resolution_from_reading(reading: FieldReading, provenance: str) -> FieldResolution:
    tier, values = reading.best_tier_values()
    if values:
        status = "ok" if len(values) == 1 else "ambiguous"
        return FieldResolution(status, values, provenance, tier, reading.all_values(), list(values))
    return FieldResolution("malformed" if reading.malformed else "missing", seen=[])


def _merge_resolutions(current: FieldResolution, new: FieldResolution) -> FieldResolution:
    seen = _union(current.seen, new.seen)
    competing = _union(current.competing, new.competing)
    if current.status == "conflict":
        return replace(current, seen=seen, competing=competing)
    if not current.values and not new.values:
        malformed = "malformed" in (current.status, new.status)
        return FieldResolution("malformed" if malformed else "missing", seen=seen)
    if not new.values:
        return replace(current, seen=seen, competing=competing)
    if not current.values:
        return FieldResolution(new.status, new.values, "second_read", new.tier, seen, competing)
    agreed = [value for value in current.values if value in new.values]
    tier = min(t for t in (current.tier, new.tier) if t is not None)
    if len(agreed) == 1:
        return FieldResolution("ok", agreed, "confirmed", tier, seen, competing)
    if len(agreed) > 1:
        return FieldResolution("ambiguous", agreed, "confirmed", tier, seen, competing)
    # Letture che non hanno alcun valore in comune: nessuna delle due è affidabile.
    return FieldResolution("conflict", [], "", None, seen, competing)


class ClosureExtraction:
    """Stato dell'estrazione: una prima lettura e le eventuali letture successive."""

    def __init__(self, text: str):
        parsed = parse_text(text)
        self.fields = {
            name: _resolution_from_reading(parsed.fields[name], "first_read")
            for name in FIELD_NAMES
        }
        self.other_payments = parsed.other_payments
        self.second_read = "not_needed"
        self.attempts: list[str] = []
        self._apply_arithmetic()

    def merge_text(self, text: str, attempt_name: str) -> None:
        parsed = parse_text(text)
        for name in FIELD_NAMES:
            new = _resolution_from_reading(parsed.fields[name], "second_read")
            self.fields[name] = _merge_resolutions(self.fields[name], new)
        if not self.other_payments:
            self.other_payments = parsed.other_payments
        self.attempts.append(attempt_name)
        self.second_read = "performed"
        self._apply_arithmetic()

    def mark_second_read_unavailable(self) -> None:
        if not self.attempts:
            self.second_read = "unavailable"

    @property
    def other_payments_total(self) -> Decimal:
        return sum((amount for _, amount in self.other_payments), Decimal("0.00"))

    def _apply_arithmetic(self) -> None:
        """Sceglie tra candidati già letti usando la sola aritmetica; non crea valori."""
        others = self.other_payments_total
        total = self.fields["total_amount"]
        cash = self.fields["cash_amount"]
        card = self.fields["card_amount"]
        for target, counterpart in ((cash, card), (card, cash)):
            if target.status in {"ambiguous", "conflict"} and total.value is not None:
                if counterpart.value is not None:
                    expected = total.value - counterpart.value - others
                    self._pick_candidate(target, expected)
        if total.status in {"ambiguous", "conflict"} and cash.value is not None:
            if card.value is not None:
                self._pick_candidate(total, cash.value + card.value + others)

    @staticmethod
    def _pick_candidate(resolution: FieldResolution, expected: Decimal) -> None:
        matching = [value for value in resolution.seen if value == expected]
        if len(matching) == 1:
            resolution.status = "ok"
            resolution.values = matching
            resolution.provenance = "arithmetic"

    def _total_corroborated(self) -> bool:
        total, cash, card = (self.fields[n].value for n in ("total_amount", "cash_amount", "card_amount"))
        if None in (total, cash, card):
            return False
        return cash + card + self.other_payments_total == total

    def payment_problems(self) -> list[str]:
        total = self.fields["total_amount"].value
        cash = self.fields["cash_amount"].value
        card = self.fields["card_amount"].value
        if total is None:
            return []
        others = self.other_payments_total
        if cash is not None and card is not None:
            return [] if cash + card + others == total else ["payments:total_mismatch"]
        present = cash if cash is not None else card
        if present is not None and present + others != total:
            return ["payments:incomplete"]
        return []

    def problems(self, today: dt.date | None = None) -> list[str]:
        today = today or dt.date.today()
        problems: list[str] = []
        for name in FIELD_NAMES:
            resolution = self.fields[name]
            if resolution.status in {"ambiguous", "conflict", "malformed"}:
                problems.append(f"{name}:{resolution.status}")
            elif resolution.status == "missing" and name in REQUIRED_FIELDS:
                problems.append(f"{name}:missing")
            if resolution.status == "ok" and len(resolution.competing) > 1:
                # Risolto per aritmetica o per intersezione tra letture, ma altri valori
                # sono stati letti: una lettura che non vede un candidato non lo smentisce.
                problems.append(f"{name}:resolved_among_alternatives")
        date_value = self.fields["date"].value
        if date_value is not None and date_value > today + dt.timedelta(days=1):
            problems.append("date:in_future")
        problems.extend(self.payment_problems())
        total = self.fields["total_amount"]
        if total.value is not None and total.tier == WEAK_TIER and not self._total_corroborated():
            problems.append("total_amount:generic_label")
        return problems

    def needs_second_read(self, today: dt.date | None = None) -> bool:
        return bool(self.problems(today))

    def to_result(self, today: dt.date | None = None) -> dict:
        problems = self.problems(today)
        values = {name: self.fields[name].value for name in FIELD_NAMES}
        if "date:in_future" in problems:
            values["date"] = None
        unresolved = [name for name in FIELD_NAMES if values[name] is None]
        total = self.fields["total_amount"]
        diagnostics = {
            "second_read": self.second_read,
            "attempts": list(self.attempts),
            "anomalies": problems,
            "unresolved_fields": unresolved,
            "fields": {
                name: {
                    "status": self.fields[name].status,
                    "provenance": self.fields[name].provenance,
                    "alternatives": [str(v) for v in self.fields[name].seen],
                    "competing": [str(v) for v in self.fields[name].competing],
                }
                for name in FIELD_NAMES
            },
            "other_payments": [
                {"label": label, "amount": amount} for label, amount in self.other_payments
            ],
            "other_payments_total": self.other_payments_total,
            "total_label": "generic" if total.tier == WEAK_TIER else "explicit",
            "total_corroborated": self._total_corroborated(),
        }
        return {**values, "diagnostics": diagnostics}


def public_summary(diagnostics: dict) -> dict:
    """Parte serializzabile della diagnostica, restituita dall'API."""
    return {
        "second_read": diagnostics.get("second_read", "unavailable"),
        "unresolved_fields": diagnostics.get("unresolved_fields", []),
        "anomalies": diagnostics.get("anomalies", []),
        "other_payments": [
            {"label": item["label"], "amount": str(item["amount"])}
            for item in diagnostics.get("other_payments", [])
        ],
    }
