from django.test import TestCase

from aggrid_ssrm.fields import FieldDef
from aggrid_ssrm.sorting import get_order_fields


class SortingTest(TestCase):
    def setUp(self):
        self.fields = {
            'name': FieldDef('name', 'name'),
            'status': FieldDef('status', 'status'),
            'updated_at': FieldDef('updated_at', 'updated_at', field_type='date'),
            'unsortable': FieldDef('unsortable', 'unsortable', sortable=False),
        }
        self.default = ['-pk']

    def test_single_asc(self):
        sm = [{'colId': 'name', 'sort': 'asc'}]
        self.assertEqual(get_order_fields(sm, self.fields, self.default), ['name'])

    def test_single_desc(self):
        sm = [{'colId': 'name', 'sort': 'desc'}]
        self.assertEqual(get_order_fields(sm, self.fields, self.default), ['-name'])

    def test_multi_column(self):
        sm = [{'colId': 'status', 'sort': 'asc'}, {'colId': 'updated_at', 'sort': 'desc'}]
        self.assertEqual(
            get_order_fields(sm, self.fields, self.default),
            ['status', '-updated_at'],
        )

    def test_empty_sort_returns_default(self):
        self.assertEqual(get_order_fields([], self.fields, self.default), ['-pk'])

    def test_unknown_column_skipped(self):
        sm = [{'colId': 'nonexistent', 'sort': 'asc'}]
        self.assertEqual(get_order_fields(sm, self.fields, self.default), ['-pk'])

    def test_unsortable_column_skipped(self):
        sm = [{'colId': 'unsortable', 'sort': 'asc'}]
        self.assertEqual(get_order_fields(sm, self.fields, self.default), ['-pk'])

    def test_mixed_valid_and_invalid(self):
        sm = [
            {'colId': 'name', 'sort': 'asc'},
            {'colId': 'nonexistent', 'sort': 'desc'},
            {'colId': 'status', 'sort': 'desc'},
        ]
        self.assertEqual(
            get_order_fields(sm, self.fields, self.default),
            ['name', '-status'],
        )
