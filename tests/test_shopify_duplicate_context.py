import csv
import io

from csv_rescue.core import clean


def make_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            'Handle',
            'Title',
            'Variant SKU',
            'Variant Price',
            'Option1 Value',
        ],
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def test_duplicate_sku_within_product_shows_variant_context():
    content = make_csv([
        {
            'Handle': 'test-shirt',
            'Title': 'Test Shirt',
            'Variant SKU': 'SHIRT-S',
            'Variant Price': '39.99',
            'Option1 Value': 'S',
        },
        {
            'Handle': 'test-shirt',
            'Title': '',
            'Variant SKU': 'SHIRT-S',
            'Variant Price': '39.99',
            'Option1 Value': '5XL',
        },
    ])

    result = clean(content, [
        {'operation': 'flag_duplicate', 'column': 'Variant SKU'}
    ])

    assert result['input_rows'] == 2
    assert result['output_rows'] == 2
    assert result['changes'] == []
    assert len(result['flagged']) == 1

    issue = result['flagged'][0]

    assert issue['row'] == 3
    assert issue['reason'] == 'Duplicate Shopify variant SKU'
    assert 'test-shirt' in issue['note']
    assert 'row 2: S' in issue['note']
    assert 'row 3: 5XL' in issue['note']


def test_duplicate_sku_across_products_identifies_both_handles():
    content = make_csv([
        {
            'Handle': 'first-shirt',
            'Title': 'First Shirt',
            'Variant SKU': 'SHARED-SKU',
            'Variant Price': '39.99',
            'Option1 Value': 'M',
        },
        {
            'Handle': 'second-shirt',
            'Title': 'Second Shirt',
            'Variant SKU': 'SHARED-SKU',
            'Variant Price': '39.99',
            'Option1 Value': 'L',
        },
    ])

    result = clean(content, [
        {'operation': 'flag_duplicate', 'column': 'Variant SKU'}
    ])

    assert len(result['flagged']) == 1

    issue = result['flagged'][0]

    assert issue['reason'] == 'Duplicate Shopify variant SKU'
    assert 'first-shirt' in issue['note']
    assert 'second-shirt' in issue['note']
    assert 'input row 2' in issue['note']
    assert 'intentional' in issue['note']
    