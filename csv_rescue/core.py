"""Conservative, auditable CSV cleaning. No AI-generated code execution."""
import csv
import io
import re
from collections import Counter
from datetime import datetime

ALLOWED = {'trim_whitespace', 'normalize_blank', 'normalize_currency', 'normalize_date', 'deduplicate'}
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


def clean(content: str, rules: list[dict]):
    columns, original = read_csv(content)
    rows = [dict(row) for row in original]
    changes, flagged = [], []
    for rule in rules:
        op = rule.get('operation')
        col = rule.get('column')
        if op not in ALLOWED:
            raise ValueError(f'Unsupported operation: {op}')
        if op != 'deduplicate' and col not in columns:
            raise ValueError(f'Unknown column: {col}')
        if op == 'deduplicate':
            keys = rule.get('columns', columns)
            if not keys or any(key not in columns for key in keys):
                raise ValueError('Invalid deduplication columns')
            seen, retained = set(), []
            for idx, row in enumerate(rows, 2):
                key = tuple(row[k] for k in keys)
                if key in seen:
                    flagged.append({'row': idx, 'reason': 'Duplicate record omitted', 'data': row})
                else:
                    seen.add(key)
                    retained.append(row)
            rows = retained
            continue
        for idx, row in enumerate(rows, 2):
            before = row[col]
            after = before
            if op == 'trim_whitespace':
                after = before.strip()
            elif op == 'normalize_blank':
                if before.strip().lower() in ('n/a', 'na', 'null', 'none', '-'):
                    after = ''
            elif op == 'normalize_currency':
                if before.strip():
                    candidate = before.strip().replace(',', '').replace('$', '')
                    if re.fullmatch(r'-?\d+(?:\.\d{1,2})?', candidate):
                        after = f'{float(candidate):.2f}'
                    else:
                        flagged.append({'row': idx, 'column': col, 'value': before, 'reason': 'Ambiguous currency'})
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
    return {'csv': output.getvalue(), 'changes': changes, 'flagged': flagged, 'input_rows': len(original), 'output_rows': len(rows)}
