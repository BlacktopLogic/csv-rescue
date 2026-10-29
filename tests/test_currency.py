import csv, pathlib
import pytest
from csv_rescue.currency import normalize_currency as n


@pytest.mark.parametrize("raw,expected", [
    # The regression: decimal commas must NOT become x100
    ("24,00", "24.00"), ("14,00", "14.00"), ("12,00", "12.00"), ("38,00", "38.00"),
    ("9,5", "9.50"), ("0,99", "0.99"), (",50", "0.50"), (".50", "0.50"),
    # Plain US-style input
    ("$18.00", "18.00"), (" $42.00 ", "42.00"), ("9", "9.00"), ("22", "22.00"),
    ("19.9", "19.90"), ("$ 12.5", "12.50"), ("USD 15", "15.00"), ("€ 7,25", "7.25"),
    # Thousands grouping
    ("1,234.56", "1234.56"), ("$1,234,567.89", "1234567.89"), ("1,234,567", "1234567.00"),
    ("1.234,56", "1234.56"), ("1.234.567", "1234567.00"),
    # Negatives
    ("-5.00", "-5.00"), ("(5.00)", "-5.00"), ("-0,00", "0.00"),
    # Non-breaking spaces from copy/paste
    ("\u00a0$10.00\u00a0", "10.00"),
])
def test_ok(raw, expected):
    r = n(raw)
    assert r.status == "ok" and r.value == expected


@pytest.mark.parametrize("raw", ["1,234", "1.234", "12,345", "999,999"])
def test_ambiguous_is_never_guessed(raw):
    r = n(raw)
    assert r.status == "ambiguous" and r.value is None and r.note


@pytest.mark.parametrize("raw", ["abc", "$", "12,", "1,2345", "1,23,456", "1.2.3", "12,34.567", "--5", "N/A"])
def test_invalid_left_for_review(raw):
    r = n(raw)
    assert r.status == "invalid" and r.value is None


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_blank(raw):
    r = n(raw)
    assert r.status == "blank" and r.value == ""


def test_changed_flag():
    assert n("$18.00").changed is True
    assert n("18.00").changed is False

