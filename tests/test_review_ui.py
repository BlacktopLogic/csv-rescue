from csv_rescue.app import HTML, app
from csv_rescue.core import clean
from fastapi.testclient import TestClient

def test_review_ui_has_sensible_rules_and_change_highlights():
    assert "send('/recommend')" in HTML
    assert 'columns.flatMap' not in HTML
    assert 'changed-cell' in HTML
    assert 'Warnings requiring review' in HTML
    assert 'Automatic corrections' in HTML

def test_source_rows_survive_deduplication():
    sample='Name,Price\n A ,10\n A ,10\n B ,20\n'
    rules=[{'operation':'trim_whitespace','column':'Name'},{'operation':'deduplicate','columns':['Name','Price']}]
    result=clean(sample,rules)
    assert result['source_rows']==[2,4]

def test_preview_returns_source_rows():
    client=TestClient(app)
    response=client.post('/preview',files={'file':('sample.csv','Name,Price\n A ,10\n A ,10\n B ,20\n','text/csv')},data={'rules':'[{"operation":"trim_whitespace","column":"Name"},{"operation":"deduplicate","columns":["Name","Price"]}]'})
    assert response.status_code==200
    assert response.json()['output_source_rows']==[2,4]
