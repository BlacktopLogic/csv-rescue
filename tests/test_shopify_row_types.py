
import csv
import io

from csv_rescue.core import clean, shopify_row_type


def make_csv(rows):
    columns = [
        "Handle", "Title", "Variant SKU", "Variant Price",
        "Variant Barcode", "Image Src", "Option1 Value",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def test_image_only_row():
    row = {
        "Handle": "test-product",
        "Image Src": "https://example.com/image.jpg",
    }
    assert shopify_row_type(row) == "image_only"


def test_variant_with_image():
    row = {
        "Handle": "test-product",
        "Variant SKU": "ABC123",
        "Image Src": "https://example.com/image.jpg",
    }
    assert shopify_row_type(row) == "variant"


def test_variant_without_sku():
    row = {
        "Handle": "test-product",
        "Variant Price": "19.99",
    }
    assert shopify_row_type(row) == "variant"


def test_unclear_row():
    row = {"Handle": "test-product"}
    assert shopify_row_type(row) == "unclear"


def test_shopify_blank_warnings_preserve_rows():
    content = make_csv([
        {
            "Handle": "test-product",
            "Title": "Test Product",
            "Variant SKU": "ABC123",
            "Variant Price": "19.99",
        },
        {
            "Handle": "test-product",
            "Image Src": "https://example.com/second.jpg",
        },
        {
            "Handle": "test-product",
            "Variant Barcode": "123456789012",
        },
        {
            "Handle": "test-product",
            "Option1 Value": "Large",
        },
    ])

    rules = [
        {"operation": "flag_blank", "column": "Title"},
        {"operation": "flag_blank", "column": "Variant SKU"},
        {"operation": "flag_blank", "column": "Variant Price"},
    ]

    result = clean(content, rules)

    assert result["input_rows"] == 4
    assert result["output_rows"] == 4
    assert result["changes"] == []

    issues = result["flagged"]

    assert not any(
        issue["row"] == 3 and issue["column"] in ("Variant SKU", "Variant Price")
        for issue in issues
    )

    assert not any(issue["column"] == "Variant SKU" for issue in issues)

    assert any(
        issue["row"] == 4 and issue["column"] == "Variant Price"
        for issue in issues
    )

    assert any(
        issue["row"] == 5 and issue["column"] == "Variant Price"
        for issue in issues
    )
