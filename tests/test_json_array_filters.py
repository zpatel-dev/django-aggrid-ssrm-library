"""
Tests for JSON array filters — _apply_json_array_filter via apply_filters.

These test filtering on fields nested inside ``payload.items[]`` using
the raw-SQL ``json_each`` approach.  Requires SQLite backend (the default).
"""
from django.test import TestCase

from tests.test_app.models import Item, ItemData
from aggrid_ssrm.fields import FieldDef
from aggrid_ssrm.filters import apply_filters


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JSON_CFG = {
    'table': 'test_app_itemdata',
    'json_column': 'payload',
    'array_path': '$.items',
    'fk_column': 'item_id',
}


def _json_fields():
    """Field definitions including JSON-array-backed columns."""
    return {
        'COUNTY': FieldDef(
            col_id='COUNTY',
            orm_path='data__payload',
            field_type='text',
            is_json=True,
            json_array_config=_JSON_CFG,
        ),
        'ACRES': FieldDef(
            col_id='ACRES',
            orm_path='data__payload',
            field_type='number',
            is_json=True,
            json_array_config=_JSON_CFG,
        ),
        'TRACT': FieldDef(
            col_id='TRACT',
            orm_path='data__payload',
            field_type='text',
            is_json=True,
            json_array_config=_JSON_CFG,
        ),
        # Non-JSON field for cross-column tests
        'status': FieldDef('status', 'status', field_type='set'),
    }


def _create_doc(name, items, status='COMPLETED'):
    """Create a Item + ItemData with the given items array."""
    doc = Item.objects.create(
        name=name,
        status=status,
        source=f'/tmp/{name}',
    )
    ItemData.objects.create(
        item=doc,
        payload={'items': items},
        review_count=0,
    )
    return doc


def _create_doc_no_data(name, status='PENDING'):
    """Create a Item with NO ItemData at all."""
    return Item.objects.create(
        name=name,
        status=status,
        source=f'/tmp/{name}',
    )


def _create_doc_custom_data(name, payload, status='COMPLETED'):
    """Create a Item with arbitrary payload (may lack 'items')."""
    doc = Item.objects.create(
        name=name,
        status=status,
        source=f'/tmp/{name}',
    )
    ItemData.objects.create(
        item=doc,
        payload=payload,
        review_count=0,
    )
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# SET FILTER ON ARRAY FIELD
# ═══════════════════════════════════════════════════════════════════════════

class JsonArraySetFilterTest(TestCase):
    def setUp(self):
        self.doc1 = _create_doc('doc1.pdf', [
            {'COUNTY': 'ALPHA', 'ACRES': 100, 'TRACT': 'T1'},
            {'COUNTY': 'BETA', 'ACRES': 200, 'TRACT': 'T2'},
        ])
        self.doc2 = _create_doc('doc2.pdf', [
            {'COUNTY': 'BETA', 'ACRES': 50, 'TRACT': 'T3'},
        ])
        self.doc3 = _create_doc('doc3.pdf', [
            {'COUNTY': 'GAMMA', 'ACRES': 300, 'TRACT': 'T4'},
        ])
        self.qs = Item.objects.all()
        self.fields = _json_fields()

    def test_set_single_value(self):
        fm = {'COUNTY': {'filterType': 'set', 'values': ['ALPHA']}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc1.pdf')

    def test_set_multiple_values(self):
        fm = {'COUNTY': {'filterType': 'set', 'values': ['ALPHA', 'BETA']}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_set_nonexistent_value(self):
        fm = {'COUNTY': {'filterType': 'set', 'values': ['NONEXISTENT']}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 0)

    def test_set_none_values_is_noop(self):
        fm = {'COUNTY': {'filterType': 'set', 'values': None}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 3)


# ═══════════════════════════════════════════════════════════════════════════
# TEXT FILTER ON ARRAY FIELD
# ═══════════════════════════════════════════════════════════════════════════

class JsonArrayTextFilterTest(TestCase):
    def setUp(self):
        self.doc1 = _create_doc('doc1.pdf', [
            {'COUNTY': 'ALPHA', 'ACRES': 100, 'TRACT': 'T1'},
        ])
        self.doc2 = _create_doc('doc2.pdf', [
            {'COUNTY': 'BETA', 'ACRES': 200, 'TRACT': 'T2'},
        ])
        self.doc3 = _create_doc('doc3.pdf', [
            {'COUNTY': 'AURORA', 'ACRES': 150, 'TRACT': 'T3'},
        ])
        self.qs = Item.objects.all()
        self.fields = _json_fields()

    def test_contains(self):
        fm = {'COUNTY': {'filterType': 'text', 'type': 'contains', 'filter': 'LPH'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc1.pdf')

    def test_equals(self):
        fm = {'COUNTY': {'filterType': 'text', 'type': 'equals', 'filter': 'ALPHA'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc1.pdf')

    def test_starts_with(self):
        fm = {'COUNTY': {'filterType': 'text', 'type': 'startsWith', 'filter': 'A'}}
        result = apply_filters(self.qs, fm, self.fields)
        # ALPHA and AURORA
        self.assertEqual(result.count(), 2)

    def test_not_contains(self):
        fm = {'COUNTY': {'filterType': 'text', 'type': 'notContains', 'filter': 'BETA'}}
        result = apply_filters(self.qs, fm, self.fields)
        # doc1 and doc3
        self.assertEqual(result.count(), 2)

    def test_ends_with(self):
        fm = {'COUNTY': {'filterType': 'text', 'type': 'endsWith', 'filter': 'PHA'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc1.pdf')

    def test_not_equal(self):
        fm = {'COUNTY': {'filterType': 'text', 'type': 'notEqual', 'filter': 'BETA'}}
        result = apply_filters(self.qs, fm, self.fields)
        # doc1 (ALPHA) and doc3 (AURORA) have items != BETA
        self.assertEqual(result.count(), 2)

    def test_text_no_match(self):
        fm = {'COUNTY': {'filterType': 'text', 'type': 'equals', 'filter': 'ZZZZZ'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 0)


# ═══════════════════════════════════════════════════════════════════════════
# NUMBER FILTER ON ARRAY FIELD
# ═══════════════════════════════════════════════════════════════════════════

class JsonArrayNumberFilterTest(TestCase):
    def setUp(self):
        self.doc1 = _create_doc('doc1.pdf', [
            {'COUNTY': 'ALPHA', 'ACRES': 100, 'TRACT': 'T1'},
        ])
        self.doc2 = _create_doc('doc2.pdf', [
            {'COUNTY': 'BETA', 'ACRES': 200, 'TRACT': 'T2'},
        ])
        self.doc3 = _create_doc('doc3.pdf', [
            {'COUNTY': 'GAMMA', 'ACRES': 50, 'TRACT': 'T3'},
        ])
        self.qs = Item.objects.all()
        self.fields = _json_fields()

    def test_greater_than(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'greaterThan', 'filter': 50}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_equals(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'equals', 'filter': 100}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc1.pdf')

    def test_in_range(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'inRange', 'filter': 50, 'filterTo': 150}}
        result = apply_filters(self.qs, fm, self.fields)
        # 50, 100 match; 200 does not
        self.assertEqual(result.count(), 2)

    def test_less_than_or_equal(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'lessThanOrEqual', 'filter': 100}}
        result = apply_filters(self.qs, fm, self.fields)
        # 50 and 100
        self.assertEqual(result.count(), 2)

    def test_less_than(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'lessThan', 'filter': 100}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc3.pdf')

    def test_not_equal(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'notEqual', 'filter': 100}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_greater_than_or_equal(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'greaterThanOrEqual', 'filter': 100}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)


# ═══════════════════════════════════════════════════════════════════════════
# COMBINED FILTER ON ARRAY FIELD
# ═══════════════════════════════════════════════════════════════════════════

class JsonArrayCombinedFilterTest(TestCase):
    def setUp(self):
        self.doc1 = _create_doc('doc1.pdf', [
            {'COUNTY': 'ALPHA', 'ACRES': 100, 'TRACT': 'T1'},
        ])
        self.doc2 = _create_doc('doc2.pdf', [
            {'COUNTY': 'BETA', 'ACRES': 200, 'TRACT': 'T2'},
        ])
        self.doc3 = _create_doc('doc3.pdf', [
            {'COUNTY': 'GAMMA', 'ACRES': 300, 'TRACT': 'T3'},
        ])
        self.qs = Item.objects.all()
        self.fields = _json_fields()

    def test_or_county_alpha_or_beta(self):
        fm = {'COUNTY': {
            'operator': 'OR',
            'condition1': {'filterType': 'text', 'type': 'equals', 'filter': 'ALPHA'},
            'condition2': {'filterType': 'text', 'type': 'equals', 'filter': 'BETA'},
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_and_county_contains_a_and_starts_a(self):
        fm = {'COUNTY': {
            'operator': 'AND',
            'condition1': {'filterType': 'text', 'type': 'contains', 'filter': 'A'},
            'condition2': {'filterType': 'text', 'type': 'startsWith', 'filter': 'A'},
        }}
        result = apply_filters(self.qs, fm, self.fields)
        # Only ALPHA starts with and contains MC
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc1.pdf')

    def test_or_where_one_condition_matches_nothing(self):
        fm = {'COUNTY': {
            'operator': 'OR',
            'condition1': {'filterType': 'text', 'type': 'equals', 'filter': 'ALPHA'},
            'condition2': {'filterType': 'text', 'type': 'equals', 'filter': 'NONEXISTENT'},
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)

    def test_and_where_conditions_conflict(self):
        fm = {'COUNTY': {
            'operator': 'AND',
            'condition1': {'filterType': 'text', 'type': 'equals', 'filter': 'ALPHA'},
            'condition2': {'filterType': 'text', 'type': 'equals', 'filter': 'BETA'},
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 0)


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-COLUMN (JSON + DIRECT FIELD)
# ═══════════════════════════════════════════════════════════════════════════

class JsonArrayMultiColumnTest(TestCase):
    def setUp(self):
        self.doc1 = _create_doc('doc1.pdf', [
            {'COUNTY': 'ALPHA', 'ACRES': 100, 'TRACT': 'T1'},
        ], status='COMPLETED')
        self.doc2 = _create_doc('doc2.pdf', [
            {'COUNTY': 'ALPHA', 'ACRES': 200, 'TRACT': 'T2'},
        ], status='PENDING')
        self.doc3 = _create_doc('doc3.pdf', [
            {'COUNTY': 'BETA', 'ACRES': 50, 'TRACT': 'T3'},
        ], status='COMPLETED')
        self.qs = Item.objects.all()
        self.fields = _json_fields()

    def test_json_county_plus_status_filter(self):
        """Filter COUNTY=ALPHA AND status=COMPLETED => doc1 only."""
        fm = {
            'COUNTY': {'filterType': 'set', 'values': ['ALPHA']},
            'status': {'filterType': 'set', 'values': ['COMPLETED']},
        }
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc1.pdf')

    def test_two_json_array_fields(self):
        """Filter COUNTY=ALPHA AND ACRES > 150 => doc2 only."""
        fm = {
            'COUNTY': {'filterType': 'set', 'values': ['ALPHA']},
            'ACRES': {'filterType': 'number', 'type': 'greaterThan', 'filter': 150},
        }
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'doc2.pdf')

    def test_json_plus_status_no_overlap(self):
        """Filter COUNTY=BETA AND status=PENDING => no match."""
        fm = {
            'COUNTY': {'filterType': 'set', 'values': ['BETA']},
            'status': {'filterType': 'set', 'values': ['PENDING']},
        }
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 0)


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class JsonArrayEdgeCaseTest(TestCase):
    def setUp(self):
        # Doc with normal items
        self.doc_normal = _create_doc('normal.pdf', [
            {'COUNTY': 'ALPHA', 'ACRES': 100, 'TRACT': 'T1'},
        ])
        # Doc with empty items array
        self.doc_empty = _create_doc('empty_items.pdf', [])
        # Doc with no 'items' key at all
        self.doc_no_key = _create_doc_custom_data(
            'no_items_key.pdf', {'other_data': 'hello'},
        )
        # Doc with no ItemData at all
        self.doc_no_data = _create_doc_no_data('no_data.pdf')
        self.qs = Item.objects.all()
        self.fields = _json_fields()

    def test_doc_with_empty_items_excluded_from_set_filter(self):
        fm = {'COUNTY': {'filterType': 'set', 'values': ['ALPHA']}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'normal.pdf')

    def test_doc_with_no_items_key_excluded_from_text_filter(self):
        fm = {'COUNTY': {'filterType': 'text', 'type': 'contains', 'filter': 'PH'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'normal.pdf')

    def test_doc_with_no_data_excluded_from_number_filter(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'greaterThan', 'filter': 0}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'normal.pdf')

    def test_all_docs_filtered_out_returns_empty(self):
        fm = {'COUNTY': {'filterType': 'set', 'values': ['NONEXISTENT']}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 0)

    def test_set_with_empty_values_list_returns_empty(self):
        fm = {'COUNTY': {'filterType': 'set', 'values': []}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 0)


class JsonArrayDocWithMultipleItemsTest(TestCase):
    """Ensure a doc with multiple items matches if ANY item matches."""

    def setUp(self):
        self.doc = _create_doc('multi.pdf', [
            {'COUNTY': 'ALPHA', 'ACRES': 50, 'TRACT': 'T1'},
            {'COUNTY': 'BETA', 'ACRES': 200, 'TRACT': 'T2'},
            {'COUNTY': 'GAMMA', 'ACRES': 100, 'TRACT': 'T3'},
        ])
        self.qs = Item.objects.all()
        self.fields = _json_fields()

    def test_set_matches_any_item(self):
        fm = {'COUNTY': {'filterType': 'set', 'values': ['BETA']}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)

    def test_number_matches_any_item(self):
        fm = {'ACRES': {'filterType': 'number', 'type': 'greaterThan', 'filter': 150}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)

    def test_distinct_result_no_duplicates(self):
        """Even if multiple items match, the doc should appear only once."""
        fm = {'COUNTY': {'filterType': 'set', 'values': ['ALPHA', 'BETA', 'GAMMA']}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
