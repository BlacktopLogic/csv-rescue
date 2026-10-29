"""Conservative column-aware cleaning recommendations and server-side guardrails."""
import re
from .profiler import profile_csv

PRICE = re.compile(r'(?:^|[ _-])(price|cost|amount|subtotal|total|compare at price)(?:$|[ _-])', re.I)
DATE = re.compile(r'(?:^|[ _-])(date|created at|updated at|timestamp)(?:$|[ _-])', re.I)
BOOL = re.compile(r'(?:^|[ _-])(published|active|enabled|taxable|requires shipping|gift card|available)(?:$|[ _-])', re.I)
IDENT = re.compile(r'(?:^|[ _-])(sku|identifier|product id|variant id)(?:$|[ _-])', re.I)
BARCODE = re.compile(r'(?:^|[ _-])(barcode|gtin|upc|ean)(?:$|[ _-])', re.I)
REQUIRED = re.compile(r'(?:^|[ _-])(price|sku|title|handle)(?:$|[ _-])', re.I)


def recommend(content):
    profile = profile_csv(content)
    rules = []
    for col, stats in profile['columns'].items():
        values = [str(x).strip().lower() for x in stats['sample_values']]
        if stats['whitespace_count']:
            rules.append({'operation':'trim_whitespace','column':col})
        if stats['placeholder_count']:
            rules.append({'operation':'normalize_blank','column':col})
        if PRICE.search(col) and stats['currency_valid'] and stats['currency_valid'] >= .8 * max(1, profile['total_rows'] - stats['blank_count']):
            rules.append({'operation':'normalize_currency','column':col})
        if DATE.search(col) and stats['date_valid'] and stats['date_valid'] >= .8 * max(1, profile['total_rows'] - stats['blank_count']):
            rules.append({'operation':'normalize_date','column':col})
        if BOOL.search(col) and values and all(v in ('yes','no','true','false','') for v in values):
            rules.append({'operation':'normalize_boolean','column':col})
        if IDENT.search(col):
            rules.append({'operation':'flag_duplicate','column':col})
        if BARCODE.search(col):
            rules.append({'operation':'flag_barcode','column':col})
        if REQUIRED.search(col):
            rules.append({'operation':'flag_blank','column':col})
    if {'Handle', 'Title', 'Variant SKU'}.issubset(profile['columns']):
        rules.append({'operation':'flag_shopify_handle','column':'Handle'})
    if profile['exact_duplicate_rows']:
        rules.append({'operation':'deduplicate','columns':list(profile['columns'])})
    return list(dict((str(r),r) for r in rules).values())


def compatible(rule, columns):
    op = rule['operation']
    if op == 'deduplicate':
        return rule.get('columns') == columns
    col = rule['column']
    if op == 'normalize_currency': return bool(PRICE.search(col))
    if op == 'normalize_date': return bool(DATE.search(col))
    if op == 'normalize_boolean': return bool(BOOL.search(col))
    if op == 'flag_duplicate': return bool(IDENT.search(col))
    if op == 'flag_barcode': return bool(BARCODE.search(col))
    if op == 'flag_shopify_handle': return col == 'Handle' and {'Handle', 'Title', 'Variant SKU'}.issubset(columns)
    if op == 'flag_blank': return bool(REQUIRED.search(col))
    return True
