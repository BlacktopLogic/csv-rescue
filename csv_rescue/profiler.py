from collections import Counter
from .core import read_csv


BLANK_MARKERS = {"n/a", "na", "null", "none", "-"}
import re
from datetime import datetime

DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y/%m/%d",
)

CURRENCY_PATTERN = re.compile(
    r"-?\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
)


def detect_currency(value: str) -> bool:
    return bool(CURRENCY_PATTERN.fullmatch(value.strip()))


def detect_date(value: str) -> bool:
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(value.strip(), fmt)
            return True
        except ValueError:
            continue
    return False


def profile_csv(content: str) -> dict:
    columns, rows = read_csv(content)
    column_profiles = {}
    candidate_rules = []

    for column in columns:
        values = [row[column] for row in rows]
        stripped = [value.strip() for value in values]

        whitespace_count = sum(
            original != trimmed
            for original, trimmed in zip(values, stripped)
        )

        empty_count = sum(
            value == "" for value in stripped
        )

        placeholder_count = sum(
            value.lower() in BLANK_MARKERS
            for value in stripped
        )

        frequencies = Counter(stripped)
        nonblank = [
            value for value in stripped
            if value and value.lower() not in BLANK_MARKERS
        ]

        currency_valid = sum(
            detect_currency(value) for value in nonblank
        )

        date_valid = sum(
            detect_date(value) for value in nonblank
        )

        currency_formatted = sum(
            "$" in value or "," in value
            for value in nonblank
            if detect_currency(value)
        )

        date_non_iso = sum(
            detect_date(value)
            and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
            for value in nonblank
        )

        column_profiles[column] = {
            "empty_count": empty_count,
            "placeholder_count": placeholder_count,
            "blank_count": empty_count + placeholder_count,
            "whitespace_count": whitespace_count,
            "unique_values": len(frequencies),
            "sample_values": stripped[:5],
            "unusual_values": [
                value
                for value, count in frequencies.items()
                if count <= 2 and value
            ][:10],
            "currency_valid": currency_valid,
            "currency_formatted": currency_formatted,
            "date_valid": date_valid,
            "date_non_iso": date_non_iso,
        }

        if whitespace_count > 0:
            candidate_rules.append({
                "operation": "trim_whitespace",
                "column": column,
            })

        if placeholder_count > 0:
            candidate_rules.append({
                "operation": "normalize_blank",
                "column": column,
            })
        if (
            nonblank
            and currency_valid / len(nonblank) >= 0.8
            and currency_formatted > 0
        ):
            candidate_rules.append({
                "operation": "normalize_currency",
                "column": column,
            })

        if (
            nonblank
            and date_valid / len(nonblank) >= 0.8
            and date_non_iso > 0
        ):
            candidate_rules.append({
                "operation": "normalize_date",
                "column": column,
            })    

    row_counts = Counter(
        tuple(row[column] for column in columns)
        for row in rows
    )

    duplicate_count = sum(
        count - 1
        for count in row_counts.values()
        if count > 1
    )

    if duplicate_count > 0:
        candidate_rules.append({
            "operation": "deduplicate",
            "columns": columns,
        })

    return {
        "total_rows": len(rows),
        "columns": column_profiles,
        "exact_duplicate_rows": duplicate_count,
        "candidate_rules": candidate_rules,
    }