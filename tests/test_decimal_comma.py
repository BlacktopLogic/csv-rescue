"""Regression: decimal commas must never be read as thousands separators."""
from csv_rescue.core import clean, read_csv
from csv_rescue.profiler import profile_csv

RULE = [{"operation": "normalize_currency", "column": "Price"}]


def test_decimal_comma_is_converted_not_multiplied():
    result = clean('Price\n"24,00"\n"9,5"\n$18.00\n', RULE)
    _, rows = read_csv(result["csv"])
    assert [r["Price"] for r in rows] == ["24.00", "9.50", "18.00"]
    assert result["flagged"] == []


def test_ambiguous_thousands_or_decimal_is_flagged_not_guessed():
    result = clean('Price\n"1,234"\n', RULE)
    _, rows = read_csv(result["csv"])
    assert rows[0]["Price"] == "1,234"
    assert result["flagged"][0]["reason"] == "Ambiguous currency"
    assert "confirm" in result["flagged"][0]["note"]


def test_us_and_european_grouping():
    result = clean('Price\n"$1,234.56"\n"1.234,56"\n', RULE)
    _, rows = read_csv(result["csv"])
    assert [r["Price"] for r in rows] == ["1234.56", "1234.56"]


def test_profiler_recognizes_decimal_comma_column():
    content = 'Price\n"24,00"\n"14,00"\n"12,00"\n"9,50"\n"7,25"\n'
    rules = profile_csv(content)["candidate_rules"]
    assert {"operation": "normalize_currency", "column": "Price"} in rules
