from csv_rescue.core import clean

def test_cleaning_and_audit():
    raw = 'Customer,Amount,Date\n Alice ,"$1,200.00",10/20/2026\nBob,unknown,not a date\n'
    result = clean(raw, [{'operation':'trim_whitespace','column':'Customer'}, {'operation':'normalize_currency','column':'Amount'}, {'operation':'normalize_date','column':'Date'}])
    assert 'Alice,1200.00,2026-10-20' in result['csv']
    assert len(result['changes']) == 3
    assert len(result['flagged']) == 2

def test_deduplication_is_reported():
    result = clean('ID,Name\n1,A\n1,A\n', [{'operation':'deduplicate','columns':['ID']}])
    assert result['output_rows'] == 1
    assert len(result['flagged']) == 1
