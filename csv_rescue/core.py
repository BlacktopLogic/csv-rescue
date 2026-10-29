"""Conservative, auditable CSV cleaning. No AI-generated code execution."""
import csv
import io
import json
import re
from collections import Counter
from datetime import datetime

from .currency import normalize_currency as _normalize_currency

ALLOWED = {'trim_whitespace', 'normalize_blank', 'normalize_currency', 'normalize_date', 'deduplicate', 'normalize_boolean', 'flag_blank', 'flag_duplicate', 'flag_barcode', 'flag_shopify_handle'}
DATE_FORMATS = ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d')


def read_csv(content: str):
    reader = csv.DictReader(io.StringIO(content, newline=''))
    if not reader.fieldnames or any(not name for name in reader.fieldnames):
        raise ValueError('CSV must contain named columns')
    if len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('CSV has duplicate column names')
    rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError('CSV contains rows with extra fields')
    return reader.fieldnames, rows

def shopify_row_type(row):
    """Conservatively distinguish variant-bearing rows from image-only rows."""
    variant_fields = (
        'Variant SKU',
        'Variant Price',
        'Variant Barcode',
        'Variant Grams',
        'Variant Inventory Qty',
        'Option1 Value',
        'Option2 Value',
        'Option3 Value',
    )
    has_variant_data = any(
        str(row.get(field) or '').strip()
        for field in variant_fields
    )
    has_image = bool(str(row.get('Image Src') or '').strip())

    if has_variant_data:
        return 'variant'
    if has_image:
        return 'image_only'
    return 'unclear'


def clean(content: str, rules: list[dict]):
    columns, original = read_csv(content)
    rows = [dict(row) for row in original]
    changes, flagged = [], []
    source_rows = list(range(2, len(rows) + 2))
    shopify = {'Handle', 'Title', 'Variant SKU'}.issubset(columns)
    # Original product group titles, keyed by normalized handle, never inferred from other products.
    product_titles = {}
    if shopify:
        for source_row, original_row in zip(source_rows, original):
            handle = original_row['Handle'].strip()
            title = original_row['Title'].strip()
            if handle and title:
                product_titles.setdefault(handle, []).append(source_row)
    for rule in rules:
        op = rule.get('operation')
        col = rule.get('column')
        if op not in ALLOWED:
            raise ValueError(f'Unsupported operation: {op}')
        if op != 'deduplicate' and col not in columns:
            raise ValueError(f'Unknown column: {col}')
        if op == 'flag_shopify_handle':
            for source_row, row in zip(source_rows, rows):
                handle = row['Handle'].strip()
                if handle and (not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', handle)):
                    flagged.append({'row': source_row, 'column': 'Handle', 'value': row['Handle'], 'reason': 'Suspicious Shopify handle', 'note': 'Nonstandard handle format; review product grouping before changing it'})
            continue
        if op == 'flag_duplicate':
            seen = {}
            for source_row, row in zip(source_rows, rows):
                value = row[col].strip()
                if value:
                    if value in seen:
                        flagged.append({'row': source_row, 'column': col, 'value': row[col], 'reason': 'Duplicate identifier', 'note': f'First occurrence at input row {seen[value]}'})
                    else:
                        seen[value] = source_row
            continue
        if op == 'deduplicate':
            keys = rule.get('columns', columns)
            if not keys or any(key not in columns for key in keys):
                raise ValueError('Invalid deduplication columns')
            seen, retained, retained_sources = set(), [], []
            for idx, row in zip(source_rows, rows):
                key = tuple(row[k] for k in keys)
                if key in seen:
                    flagged.append({'row': idx, 'reason': 'Duplicate record omitted', 'data': row})
                else:
                    seen.add(key)
                    retained.append(row)
                    retained_sources.append(idx)
            rows, source_rows = retained, retained_sources
            continue
        for idx, row in zip(source_rows, rows):
            before = row[col]
            after = before

            if op == 'flag_blank':
                if not before.strip():
                    if shopify:
                        row_type = shopify_row_type(row)

                        # Shopify continuation rows legitimately omit the product title.
                        if col == 'Title' and row['Handle'].strip() in product_titles:
                            continue

                        # Additional image rows do not need variant fields.
                        if row_type == 'image_only' and col in ('Variant SKU', 'Variant Price'):
                            continue

                        # SKU is optional in Shopify, even for actual variants.
                        if col == 'Variant SKU':
                            continue

                        # Avoid claiming a missing price is invalid when row purpose is unclear.
                        if col == 'Variant Price' and row_type == 'unclear':
                            flagged.append({
                                'row': idx,
                                'column': col,
                                'value': before,
                                'reason': 'Unclear Shopify row type',
                                'note': 'Could not establish whether this row represents a variant; review manually'
                            })
                            continue

                    flagged.append({
                        'row': idx,
                        'column': col,
                        'value': before,
                        'reason': 'Blank required value',
                        'note': 'Review manually; no replacement inferred'
                    })

            elif op == 'flag_barcode':
                value = before.strip()
                if re.fullmatch(r'[+-]?\d+(?:\.\d+)?[eE][+-]?\d+', value):
                    flagged.append({'row': idx, 'column': col, 'value': before, 'reason': 'Scientific notation barcode', 'note': 'May have been altered by spreadsheet software; original cannot be recovered reliably'})
                elif value and (not value.isascii() or not value.isdigit()):
                    flagged.append({'row': idx, 'column': col, 'value': before, 'reason': 'Non-numeric barcode', 'note': 'Review barcode format manually'})
                elif value and len(value) not in (8, 12, 13, 14):
                    flagged.append({'row': idx, 'column': col, 'value': before, 'reason': 'Unusual barcode length', 'note': 'Expected common GTIN lengths 8, 12, 13, or 14; other formats may be valid'})
            elif op == 'normalize_boolean':
                token = before.strip().lower()
                if token in ('yes', 'true'):
                    after = 'TRUE'
                elif token in ('no', 'false'):
                    after = 'FALSE'
                elif token:
                    flagged.append({'row': idx, 'column': col, 'value': before, 'reason': 'Unrecognized boolean', 'note': 'Left unchanged'})
            elif op == 'trim_whitespace':
                after = before.strip()
            elif op == 'normalize_blank':
                if before.strip().lower() in ('n/a', 'na', 'null', 'none', '-'):
                    after = ''
            elif op == 'normalize_currency':
                if before.strip():
                    result = _normalize_currency(before)
                    if result.status == 'ok':
                        after = result.value
                    else:
                        flagged.append({'row': idx, 'column': col, 'value': before, 'reason': 'Ambiguous currency', 'note': result.note})
            elif op == 'normalize_date':
                if before.strip():
                    parsed = None
                    for fmt in DATE_FORMATS:
                        try:
                            parsed = datetime.strptime(before.strip(), fmt)
                            break
                        except ValueError:
                            pass
                    if parsed:
                        after = parsed.strftime('%Y-%m-%d')
                    else:
                        flagged.append({'row': idx, 'column': col, 'value': before, 'reason': 'Unrecognized date'})
            if after != before:
                row[col] = after
                changes.append({'row': idx, 'column': col, 'operation': op, 'before': before, 'after': after})
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return {'csv': output.getvalue(), 'changes': changes, 'flagged': flagged, 'input_rows': len(original), 'output_rows': len(rows), 'source_rows': source_rows}


def audit_csv(result):
    """Complete, spreadsheet-friendly record of applied changes and unresolved flags."""
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=['type', 'input_row', 'column', 'operation', 'before', 'after', 'reason', 'note', 'record_json'])
    writer.writeheader()
    for change in result['changes']:
        writer.writerow({'type': 'change', 'input_row': change['row'], 'column': change['column'], 'operation': change['operation'], 'before': change['before'], 'after': change['after']})
    for issue in result['flagged']:
        writer.writerow({'type': 'flag', 'input_row': issue['row'], 'column': issue.get('column', ''), 'before': issue.get('value', ''), 'reason': issue['reason'], 'note': issue.get('note', ''), 'record_json': json.dumps(issue['data'], ensure_ascii=False) if 'data' in issue else ''})
    return out.getvalue()
