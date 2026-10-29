import csv
import io
from csv_rescue.core import clean, audit_csv

def test_boolean_explicit():
    result = clean('Published\nyes\nNo\nmaybe\n', [{'operation':'normalize_boolean','column':'Published'}])
    assert [r['Published'] for r in csv.DictReader(io.StringIO(result['csv']))] == ['TRUE','FALSE','maybe']
    assert any(x['reason']=='Unrecognized boolean' for x in result['flagged'])

def test_shopify_flags_no_guessing():
    source = 'SKU,Price,Barcode\nA,,123456789012\nA,19,1.234E+12\nB,25,1234567\n'
    rules = [{'operation':'flag_blank','column':'Price'},{'operation':'flag_duplicate','column':'SKU'},{'operation':'flag_barcode','column':'Barcode'}]
    result = clean(source, rules)
    assert list(csv.DictReader(io.StringIO(result['csv']))) == list(csv.DictReader(io.StringIO(source)))
    assert {x['reason'] for x in result['flagged']} == {'Blank required value','Duplicate identifier','Scientific notation barcode','Unusual barcode length'}
    assert len(list(csv.DictReader(io.StringIO(audit_csv(result))))) == 4

def test_dedupe_preserves_source_row_numbers():
    source = 'SKU,Price\nA,1\nA,1\nB,3\n'
    result = clean(source,[{'operation':'deduplicate','columns':['SKU']},{'operation':'normalize_currency','column':'Price'}])
    assert result['flagged'][0]['row'] == 3
    assert [c['row'] for c in result['changes']] == [2,4]
    assert 'Duplicate record omitted' in audit_csv(result)

def test_complete_report_not_preview_limited():
    source='Value\n'+' x \n'*40
    result=clean(source,[{'operation':'trim_whitespace','column':'Value'}])
    assert len(list(csv.DictReader(io.StringIO(audit_csv(result))))) == 40
