"""
Comprehensive tests for aggrid_ssrm.column_values — get_distinct_values.

Covers direct fields, JSON fields (top-level and array-nested),
limit enforcement, and edge cases.
"""
from django.test import TestCase

from tests.test_app.models import Item, ItemData
from aggrid_ssrm.column_values import get_distinct_values
from aggrid_ssrm.fields import FieldDef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vg(col):
    """Value getter factory for top-level payload keys."""
    def getter(d):
        ed = d.data.payload if hasattr(d, 'data') else {}
        return ed.get(col) if isinstance(ed, dict) else None
    return getter


JSON_ARRAY_CONFIG = {
    'table': 'test_app_itemdata',
    'json_column': 'payload',
    'array_path': '$.items',
    'fk_column': 'item_id',
}


# ===========================================================================
# DIRECT FIELD DISTINCT VALUES
# ===========================================================================

class DistinctFilenamesTest(TestCase):
    def setUp(self):
        for name in ['alpha.pdf', 'beta.pdf', 'gamma.pdf']:
            Item.objects.create(
                name=name,
                status='COMPLETED', source=f'/tmp/{name}',
            )
        self.qs = Item.objects.all()
        self.fields_dict = {
            'name': FieldDef('name', 'name'),
        }

    def test_returns_all_unique_filenames_sorted(self):
        result = get_distinct_values(self.qs, 'name', self.fields_dict)
        self.assertEqual(result, ['alpha.pdf', 'beta.pdf', 'gamma.pdf'])


class DistinctStatusesTest(TestCase):
    def setUp(self):
        for i, status in enumerate(['COMPLETED', 'PENDING', 'FAILED', 'COMPLETED']):
            Item.objects.create(
                name=f'f{i}.pdf',
                status=status, source=f'/tmp/f{i}.pdf',
            )
        self.qs = Item.objects.all()
        self.fields_dict = {
            'status': FieldDef('status', 'status', field_type='set'),
        }

    def test_returns_all_unique_statuses_sorted(self):
        result = get_distinct_values(self.qs, 'status', self.fields_dict)
        self.assertEqual(result, ['COMPLETED', 'FAILED', 'PENDING'])


class DistinctExcludesNullTest(TestCase):
    def setUp(self):
        Item.objects.create(
            name='a.pdf',
            status='COMPLETED', source='/tmp/a.pdf',
            modified_at=None,
        )
        Item.objects.create(
            name='b.pdf',
            status='PENDING', source='/tmp/b.pdf',
            modified_at=None,
        )
        self.qs = Item.objects.all()
        self.fields_dict = {
            'modified_at': FieldDef(
                'modified_at', 'modified_at', field_type='date',
            ),
        }

    def test_null_values_excluded(self):
        result = get_distinct_values(
            self.qs, 'modified_at', self.fields_dict,
        )
        self.assertEqual(result, [])


class DistinctExcludesEmptyStringTest(TestCase):
    def setUp(self):
        Item.objects.create(
            name='',
            status='COMPLETED', source='/tmp/empty',
        )
        Item.objects.create(
            name='real.pdf',
            status='PENDING', source='/tmp/real.pdf',
        )
        self.qs = Item.objects.all()
        self.fields_dict = {
            'name': FieldDef('name', 'name'),
        }

    def test_empty_string_excluded(self):
        result = get_distinct_values(self.qs, 'name', self.fields_dict)
        self.assertEqual(result, ['real.pdf'])


class DistinctLimitEnforcementTest(TestCase):
    def setUp(self):
        for i in range(10):
            Item.objects.create(
                name=f'file{i:02d}.pdf',
                status='COMPLETED', source=f'/tmp/file{i:02d}.pdf',
            )
        self.qs = Item.objects.all()
        self.fields_dict = {
            'name': FieldDef('name', 'name'),
        }

    def test_limit_caps_results(self):
        result = get_distinct_values(
            self.qs, 'name', self.fields_dict, limit=3,
        )
        self.assertEqual(len(result), 3)

    def test_limit_larger_than_count_returns_all(self):
        result = get_distinct_values(
            self.qs, 'name', self.fields_dict, limit=100,
        )
        self.assertEqual(len(result), 10)


# ===========================================================================
# JSON FIELD (top-level, simple names) — ORM path fallback
# ===========================================================================

class JsonFieldDistinctStateTest(TestCase):
    def setUp(self):
        states = ['TX', 'CA', 'OK', 'TX', 'CA']
        for i, state in enumerate(states):
            doc = Item.objects.create(
                name=f'f{i}.pdf',
                status='COMPLETED', source=f'/tmp/f{i}.pdf',
            )
            ItemData.objects.create(
                item=doc,
                payload={'state': state},
            )
        self.qs = Item.objects.all().select_related('data')
        self.fields_dict = {
            'state': FieldDef(
                'state', 'data__payload__state', is_json=True,
                value_getter=_vg('state'),
            ),
        }

    def test_distinct_state_values(self):
        result = get_distinct_values(self.qs, 'state', self.fields_dict)
        self.assertEqual(result, ['CA', 'OK', 'TX'])


class JsonFieldDistinctWithNullsTest(TestCase):
    def setUp(self):
        for i, state in enumerate(['TX', None, 'CA', None]):
            doc = Item.objects.create(
                name=f'f{i}.pdf',
                status='COMPLETED', source=f'/tmp/f{i}.pdf',
            )
            ed = {'state': state} if state else {'other': 'val'}
            ItemData.objects.create(item=doc, payload=ed)
        self.qs = Item.objects.all().select_related('data')
        self.fields_dict = {
            'state': FieldDef(
                'state', 'data__payload__state', is_json=True,
                value_getter=_vg('state'),
            ),
        }

    def test_null_entries_excluded(self):
        result = get_distinct_values(self.qs, 'state', self.fields_dict)
        self.assertNotIn(None, result)
        self.assertNotIn('None', result)


class JsonFieldDistinctLimitTest(TestCase):
    def setUp(self):
        for i in range(10):
            doc = Item.objects.create(
                name=f'f{i}.pdf',
                status='COMPLETED', source=f'/tmp/f{i}.pdf',
            )
            ItemData.objects.create(
                item=doc,
                payload={'state': f'STATE_{i:02d}'},
            )
        self.qs = Item.objects.all().select_related('data')
        self.fields_dict = {
            'state': FieldDef(
                'state', 'data__payload__state', is_json=True,
                value_getter=_vg('state'),
            ),
        }

    def test_limit_on_json_values(self):
        result = get_distinct_values(
            self.qs, 'state', self.fields_dict, limit=3,
        )
        self.assertLessEqual(len(result), 3)


# ===========================================================================
# JSON FIELD (array-nested, with json_array_config)
# ===========================================================================

class JsonArrayDistinctCountyTest(TestCase):
    def setUp(self):
        doc1 = Item.objects.create(
            name='d1.pdf',
            status='COMPLETED', source='/tmp/d1.pdf',
        )
        ItemData.objects.create(
            item=doc1,
            payload={'items': [
                {'COUNTY': 'Travis', 'STATE': 'TX'},
                {'COUNTY': 'Harris', 'STATE': 'TX'},
            ]},
        )
        doc2 = Item.objects.create(
            name='d2.pdf',
            status='COMPLETED', source='/tmp/d2.pdf',
        )
        ItemData.objects.create(
            item=doc2,
            payload={'items': [
                {'COUNTY': 'Los Angeles', 'STATE': 'CA'},
                {'COUNTY': 'Travis', 'STATE': 'TX'},
            ]},
        )
        self.qs = Item.objects.all().select_related('data')
        self.fields_dict = {
            'COUNTY': FieldDef(
                'COUNTY', 'data__payload__COUNTY', is_json=True,
                json_array_config=JSON_ARRAY_CONFIG,
            ),
            'STATE': FieldDef(
                'STATE', 'data__payload__STATE', is_json=True,
                json_array_config=JSON_ARRAY_CONFIG,
            ),
        }

    def test_distinct_county_from_items(self):
        result = get_distinct_values(self.qs, 'COUNTY', self.fields_dict)
        self.assertEqual(result, ['Harris', 'Los Angeles', 'Travis'])

    def test_distinct_state_from_items(self):
        result = get_distinct_values(self.qs, 'STATE', self.fields_dict)
        self.assertEqual(result, ['CA', 'TX'])


class JsonArrayDuplicatesDeduplicatedTest(TestCase):
    def setUp(self):
        doc = Item.objects.create(
            name='dup.pdf',
            status='COMPLETED', source='/tmp/dup.pdf',
        )
        ItemData.objects.create(
            item=doc,
            payload={'items': [
                {'COUNTY': 'Travis'},
                {'COUNTY': 'Travis'},
                {'COUNTY': 'Travis'},
            ]},
        )
        self.qs = Item.objects.all().select_related('data')
        self.fields_dict = {
            'COUNTY': FieldDef(
                'COUNTY', 'data__payload__COUNTY', is_json=True,
                json_array_config=JSON_ARRAY_CONFIG,
            ),
        }

    def test_duplicates_across_items_deduplicated(self):
        result = get_distinct_values(self.qs, 'COUNTY', self.fields_dict)
        self.assertEqual(result, ['Travis'])


class JsonArrayExcludesNullItemsTest(TestCase):
    def setUp(self):
        doc = Item.objects.create(
            name='nulls.pdf',
            status='COMPLETED', source='/tmp/nulls.pdf',
        )
        ItemData.objects.create(
            item=doc,
            payload={'items': [
                {'COUNTY': 'Travis'},
                {'COUNTY': None},
                {'COUNTY': ''},
                {'other_key': 'val'},
            ]},
        )
        self.qs = Item.objects.all().select_related('data')
        self.fields_dict = {
            'COUNTY': FieldDef(
                'COUNTY', 'data__payload__COUNTY', is_json=True,
                json_array_config=JSON_ARRAY_CONFIG,
            ),
        }

    def test_null_and_empty_items_excluded(self):
        result = get_distinct_values(self.qs, 'COUNTY', self.fields_dict)
        self.assertEqual(result, ['Travis'])


class JsonArrayLimitTest(TestCase):
    def setUp(self):
        doc = Item.objects.create(
            name='many.pdf',
            status='COMPLETED', source='/tmp/many.pdf',
        )
        items = [{'COUNTY': f'County_{i:02d}'} for i in range(20)]
        ItemData.objects.create(
            item=doc, payload={'items': items},
        )
        self.qs = Item.objects.all().select_related('data')
        self.fields_dict = {
            'COUNTY': FieldDef(
                'COUNTY', 'data__payload__COUNTY', is_json=True,
                json_array_config=JSON_ARRAY_CONFIG,
            ),
        }

    def test_limit_enforcement_on_array_values(self):
        result = get_distinct_values(
            self.qs, 'COUNTY', self.fields_dict, limit=5,
        )
        self.assertEqual(len(result), 5)


# ===========================================================================
# EDGE CASES
# ===========================================================================

class UnknownColumnTest(TestCase):
    def setUp(self):
        Item.objects.create(
            name='a.pdf',
            status='COMPLETED', source='/tmp/a.pdf',
        )
        self.qs = Item.objects.all()
        self.fields_dict = {
            'name': FieldDef('name', 'name'),
        }

    def test_unknown_column_returns_empty_list(self):
        result = get_distinct_values(
            self.qs, 'nonexistent', self.fields_dict,
        )
        self.assertEqual(result, [])


class EmptyQuerysetTest(TestCase):
    def setUp(self):
        self.qs = Item.objects.all()
        self.fields_dict = {
            'name': FieldDef('name', 'name'),
        }

    def test_empty_queryset_returns_empty_list(self):
        result = get_distinct_values(self.qs, 'name', self.fields_dict)
        self.assertEqual(result, [])


class AllIdenticalValuesTest(TestCase):
    def setUp(self):
        for i in range(5):
            Item.objects.create(
                name='same.pdf',
                status='COMPLETED', source=f'/tmp/same{i}.pdf',
            )
        self.qs = Item.objects.all()
        self.fields_dict = {
            'name': FieldDef('name', 'name'),
        }

    def test_all_identical_returns_one_value(self):
        result = get_distinct_values(self.qs, 'name', self.fields_dict)
        self.assertEqual(result, ['same.pdf'])


class SpecialCharsWithJsonArrayConfigTest(TestCase):
    """Column name with special chars -- json_array_config path used."""

    def setUp(self):
        doc = Item.objects.create(
            name='spec.pdf',
            status='COMPLETED', source='/tmp/spec.pdf',
        )
        ItemData.objects.create(
            item=doc,
            payload={'items': [
                {'Well Name (API)': 'W1'},
                {'Well Name (API)': 'W2'},
            ]},
        )
        self.qs = Item.objects.all().select_related('data')
        self.fields_dict = {
            'Well Name (API)': FieldDef(
                'Well Name (API)',
                'data__extracted_data__Well Name (API)',
                is_json=True,
                json_array_config=JSON_ARRAY_CONFIG,
            ),
        }

    def test_special_chars_column_with_json_array_config(self):
        result = get_distinct_values(
            self.qs, 'Well Name (API)', self.fields_dict,
        )
        self.assertEqual(result, ['W1', 'W2'])


class NonJsonFieldStandardDistinctTest(TestCase):
    def setUp(self):
        for i, status in enumerate(['COMPLETED', 'PENDING', 'FAILED']):
            Item.objects.create(
                name=f'f{i}.pdf',
                status=status, source=f'/tmp/f{i}.pdf',
            )
        self.qs = Item.objects.all()
        self.fields_dict = {
            'status': FieldDef('status', 'status', field_type='set'),
        }

    def test_non_json_uses_orm_distinct(self):
        result = get_distinct_values(self.qs, 'status', self.fields_dict)
        self.assertEqual(result, ['COMPLETED', 'FAILED', 'PENDING'])


class OrmPathFallbackTest(TestCase):
    """Field with no value_getter and no json_array_config: ORM path fallback."""

    def setUp(self):
        for i, state in enumerate(['TX', 'CA', 'OK']):
            doc = Item.objects.create(
                name=f'f{i}.pdf',
                status='COMPLETED', source=f'/tmp/f{i}.pdf',
            )
            ItemData.objects.create(
                item=doc,
                payload={'state': state},
            )
        self.qs = Item.objects.all().select_related('data')
        # No value_getter, no json_array_config — relies on ORM path
        self.fields_dict = {
            'state': FieldDef(
                'state', 'data__payload__state', is_json=True,
            ),
        }

    def test_orm_path_fallback_returns_distinct_values(self):
        result = get_distinct_values(self.qs, 'state', self.fields_dict)
        self.assertEqual(result, ['CA', 'OK', 'TX'])
