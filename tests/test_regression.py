"""Regression tests for CSV Rescue's deterministic cleaning engine.

Copy this file into the project's tests/ directory and run: python -m pytest -q
"""

import pytest

from csv_rescue.core import clean, read_csv


def apply(raw, *rules):
    return clean(raw, list(rules))


def rule(operation, column):
    return {"operation": operation, "column": column}


def test_currency_normalization_preserves_amounts():
    raw = 'Amount\n"$1,200.50"\n$25.77\n-12.5\n0\n'
    result = apply(raw, rule("normalize_currency", "Amount"))
    _, rows = read_csv(result["csv"])
    assert [r["Amount"] for r in rows] == ["1200.50", "25.77", "-12.50", "0.00"]
    assert result["flagged"] == []


def test_date_normalization_handles_supported_formats():
    raw = 'Date\n10/20/2026\n2026/10/21\n2026-10-22\n10/23/26\n'
    result = apply(raw, rule("normalize_date", "Date"))
    _, rows = read_csv(result["csv"])
    assert [r["Date"] for r in rows] == ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
    assert result["flagged"] == []


def test_ambiguous_values_are_flagged_and_unchanged():
    raw = 'Amount,Date\nunknown,not a date\n$12.345,2026-02-30\n'
    result = apply(raw, rule("normalize_currency", "Amount"), rule("normalize_date", "Date"))
    _, rows = read_csv(result["csv"])
    assert rows == [
        {"Amount": "unknown", "Date": "not a date"},
        {"Amount": "$12.345", "Date": "2026-02-30"},
    ]
    assert len(result["flagged"]) == 4
    assert {f["reason"] for f in result["flagged"]} == {"Ambiguous currency", "Unrecognized date"}


def test_blank_placeholders_normalize_without_inventing_values():
    raw = 'Notes\nN/A\nnull\n-\nnone\nactual note\n'
    result = apply(raw, rule("normalize_blank", "Notes"))
    _, rows = read_csv(result["csv"])
    assert [r["Notes"] for r in rows] == ["", "", "", "", "actual note"]
    assert len(result["changes"]) == 4


def test_exact_duplicates_removed_and_audited():
    raw = 'ID,Name\n1,Alice\n1,Alice\n2,Bob\n'
    result = apply(raw, {"operation": "deduplicate", "columns": ["ID", "Name"]})
    assert (result["input_rows"], result["output_rows"]) == (3, 2)
    assert len(result["flagged"]) == 1
    assert result["flagged"][0]["reason"] == "Duplicate record omitted"


def test_normalization_can_create_new_duplicates():
    raw = 'ID,Name\n1,Alice\n1, Alice \n'
    rules = [rule("trim_whitespace", "Name"), {"operation": "deduplicate", "columns": ["ID", "Name"]}]
    result = clean(raw, rules)
    assert result["input_rows"] == 2
    assert result["output_rows"] == 1
    assert len(result["flagged"]) == 1
    # Rule order matters: deduplicating first retains both original records.
    reversed_result = clean(raw, list(reversed(rules)))
    assert reversed_result["output_rows"] == 2


def test_commas_quotes_and_unicode_round_trip():
    raw = 'Customer,Notes\n"Nguyen, Kim","She said ""hello"""\nJosé García,café delivery\nZoë Martin,standard\n'
    result = apply(raw, rule("trim_whitespace", "Customer"))
    _, rows = read_csv(result["csv"])
    assert rows == [
        {"Customer": "Nguyen, Kim", "Notes": 'She said "hello"'},
        {"Customer": "José García", "Notes": "café delivery"},
        {"Customer": "Zoë Martin", "Notes": "standard"},
    ]


def test_cleaning_is_idempotent():
    raw = 'Customer,Amount,Date,Notes\n Alice ,"$1,200.00",10/20/2026,N/A\n Alice ,"$1,200.00",10/20/2026,N/A\n'
    rules = [
        rule("trim_whitespace", "Customer"),
        rule("normalize_currency", "Amount"),
        rule("normalize_date", "Date"),
        rule("normalize_blank", "Notes"),
        {"operation": "deduplicate", "columns": ["Customer", "Amount", "Date", "Notes"]},
    ]
    first = clean(raw, rules)
    second = clean(first["csv"], rules)
    assert second["csv"] == first["csv"]
    assert second["changes"] == []
    assert second["flagged"] == []
    assert second["input_rows"] == second["output_rows"] == 1


@pytest.mark.parametrize("raw", [
    "", "A,B\n1,2,3\n", "A,A\n1,2\n", ",B\n1,2\n",
])
def test_invalid_csv_headers_or_extra_fields_rejected(raw):
    with pytest.raises(ValueError):
        read_csv(raw)


def test_unknown_operation_rejected():
    with pytest.raises(ValueError, match="Unsupported operation"):
        apply('Name\nAlice\n', rule("make_up_data", "Name"))
