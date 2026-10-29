from csv_rescue.recommend import recommend, compatible

def test_shopify_column_rules():
    csv = 'Handle,Title,Variant Price,Variant SKU,Variant Barcode,Published\ncedar-candle, Candle ,24,ABC,123456789012,yes\nrose-candle,Rose,42,ABC,1.234E+11,no\n'
    rules = recommend(csv)
    pairs = {(r['operation'],r.get('column')) for r in rules}
    assert ('normalize_currency','Handle') not in pairs
    assert ('normalize_currency','Variant Price') in pairs
    assert ('normalize_boolean','Published') in pairs
    assert ('flag_duplicate','Variant SKU') in pairs
    assert ('flag_barcode','Variant Barcode') in pairs
    assert ('trim_whitespace','Title') in pairs
    assert all(compatible(r, list(csv.splitlines()[0].split(','))) for r in rules)

def test_incompatible_rule_rejected():
    assert not compatible({'operation':'normalize_currency','column':'Handle'}, ['Handle'])
    assert not compatible({'operation':'flag_barcode','column':'Title'}, ['Title'])
