"""Safe currency normalization for csv-rescue.

Fixes the bug where a decimal comma ("24,00") was read as a thousands
separator and became 2400.00. Ambiguous values are never guessed: they are
returned with status "ambiguous" so the caller can flag them for review.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

_SYMBOLS = re.compile(r"(?i)(usd|eur|gbp|cad|aud|us\$|[$€£¥])")
_WS = re.compile(r"[\s\u00a0\u202f]+")
_NUMBER = re.compile(r"^[\d.,]+$")


@dataclass(frozen=True)
class CurrencyResult:
    original: str
    value: Optional[str]  # normalized "1234.50", or None when not safe to change
    status: str           # "ok" | "blank" | "ambiguous" | "invalid"
    note: str = ""

    @property
    def changed(self) -> bool:
        return self.status == "ok" and self.value != self.original


def _groups_ok(part: str, sep: str) -> bool:
    """True if `part` is thousands-grouped by `sep`: 1-3 digits, then groups of exactly 3."""
    pieces = part.split(sep)
    return (
        1 <= len(pieces[0]) <= 3
        and pieces[0].isdigit()
        and all(len(p) == 3 and p.isdigit() for p in pieces[1:])
    )


def _fmt(integer: str, frac: str, negative: bool) -> str:
    try:
        d = Decimal(f"{integer or '0'}.{frac or '0'}")
    except InvalidOperation:  # pragma: no cover
        raise ValueError("unparseable")
    d = d.quantize(Decimal("0.01"))
    return f"{'-' if negative and d != 0 else ''}{d}"


def normalize_currency(raw) -> CurrencyResult:
    original = "" if raw is None else str(raw)
    s = _WS.sub(" ", original).strip()
    if s == "":
        return CurrencyResult(original, "", "blank")

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    s = _SYMBOLS.sub("", s).strip()
    if s.startswith("-"):
        negative, s = True, s[1:].strip()
    s = s.replace(" ", "")  # spaces left between symbol and number

    if not s or not _NUMBER.match(s) or not any(c.isdigit() for c in s):
        return CurrencyResult(original, None, "invalid", "not a recognizable price")

    has_c, has_d = "," in s, "." in s

    # Digits only
    if not has_c and not has_d:
        return CurrencyResult(original, _fmt(s, "", negative), "ok")

    # Both separators: the LAST one is the decimal point.
    if has_c and has_d:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        whole, _, frac = s.rpartition(dec)
        if thou in frac or dec in whole or not _groups_ok(whole, thou) or not (1 <= len(frac) <= 2) or not frac.isdigit():
            return CurrencyResult(original, None, "invalid", "mixed separators in an unexpected pattern")
        return CurrencyResult(original, _fmt(whole.replace(thou, ""), frac, negative), "ok")

    # One separator type only
    sep = "," if has_c else "."
    count = s.count(sep)

    if count > 1:  # 1,234,567 or 1.234.567 -> thousands grouping
        if _groups_ok(s, sep):
            return CurrencyResult(original, _fmt(s.replace(sep, ""), "", negative), "ok")
        return CurrencyResult(original, None, "invalid", "repeated separator in an unexpected pattern")

    whole, _, frac = s.partition(sep)
    if not whole.isdigit() and whole != "":
        return CurrencyResult(original, None, "invalid", "unexpected characters")
    if frac == "" or not frac.isdigit():
        return CurrencyResult(original, None, "invalid", "separator with no digits after it")
    if len(frac) <= 2:                      # 24,00  9,5  19.99  .50
        return CurrencyResult(original, _fmt(whole, frac, negative), "ok")
    if len(frac) == 3 and whole != "":      # 1,234 or 1.234: thousands OR decimal
        return CurrencyResult(
            original, None, "ambiguous",
            f"'{s}' could be {whole}{frac} (thousands) or {whole}.{frac} (decimal); confirm with customer",
        )
    return CurrencyResult(original, None, "invalid", "too many digits after the separator")
