from csv_rescue.core import clean
from csv_rescue.recommend import recommend, compatible

CSV = ('Handle,Title,Variant SKU,Variant Price,Variant Barcode\n'
       'product-a,Product A,SKU-1,12.00,123456789012\n'
       'product-a,,SKU-2,13.00,123456789013\n'
       'product-b,,SKU-3,,8.54E+11\n'
       'Product B,Product B,SKU-4,10.00,123456789014\n')

def test_variant_title_is_not_falsely_flagged():
    result = clean(CSV, [{'operation':'flag_blank','column':'Title'}])
    assert [f['row'] for f in result['flagged']] == [4]

def test_shopify_handles_flagged_without_rewriting():
    result = clean(CSV, [{'operation':'flag_shopify_handle','column':'Handle'}])
    assert [f['row'] for f in result['flagged']] == [5]
    assert 'Product B,Product B' in result['csv']

def test_non_shopify_titles_still_flagged():
    result = clean('Title,Other\n,abc\n', [{'operation':'flag_blank','column':'Title'}])
    assert len(result['flagged']) == 1

def test_shopify_rule_is_recommended_and_guarded():
    assert {'operation':'flag_shopify_handle','column':'Handle'} in recommend(CSV)
    assert compatible({'operation':'flag_shopify_handle','column':'Handle'}, ['Handle','Title','Variant SKU'])
    assert not compatible({'operation':'flag_shopify_handle','column':'Handle'}, ['Handle','Title'])
