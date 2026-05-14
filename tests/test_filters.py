from django.test import TestCase

from tests.test_app.models import Item, ItemData
from aggrid_ssrm.fields import FieldDef
from aggrid_ssrm.filters import apply_filters, apply_search


def _make_fields():
    return {
        'name': FieldDef('name', 'name'),
        'status': FieldDef('status', 'status', field_type='set'),
        'review_count': FieldDef('review_count', 'data__review_count', field_type='number'),
    }


class SetFilterTest(TestCase):
    def setUp(self):
        for name, status in [('a.pdf', 'COMPLETED'), ('b.pdf', 'PENDING'), ('c.pdf', 'COMPLETED')]:
            Item.objects.create(
                name=name, status=status, source=f'/tmp/{name}',
            )
        self.fields = _make_fields()

    def test_set_filter_narrows_results(self):
        qs = Item.objects.all()
        fm = {'status': {'filterType': 'set', 'values': ['COMPLETED']}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 2)

    def test_set_filter_none_values_is_noop(self):
        qs = Item.objects.all()
        fm = {'status': {'filterType': 'set', 'values': None}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 3)

    def test_set_filter_empty_values_returns_nothing(self):
        qs = Item.objects.all()
        fm = {'status': {'filterType': 'set', 'values': []}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 0)

    def test_unknown_column_skipped(self):
        qs = Item.objects.all()
        fm = {'nonexistent': {'filterType': 'set', 'values': ['x']}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 3)


class TextFilterTest(TestCase):
    def setUp(self):
        for name in ['alpha.pdf', 'beta.pdf', 'alphabet.pdf']:
            Item.objects.create(
                name=name, status='PENDING', source=f'/tmp/{name}',
            )
        self.fields = _make_fields()

    def test_contains(self):
        qs = Item.objects.all()
        fm = {'name': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 2)

    def test_not_contains(self):
        qs = Item.objects.all()
        fm = {'name': {'filterType': 'text', 'type': 'notContains', 'filter': 'alpha'}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 1)

    def test_equals(self):
        qs = Item.objects.all()
        fm = {'name': {'filterType': 'text', 'type': 'equals', 'filter': 'beta.pdf'}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 1)

    def test_starts_with(self):
        qs = Item.objects.all()
        fm = {'name': {'filterType': 'text', 'type': 'startsWith', 'filter': 'alph'}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 2)

    def test_ends_with(self):
        qs = Item.objects.all()
        fm = {'name': {'filterType': 'text', 'type': 'endsWith', 'filter': 'bet.pdf'}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 1)


class NumberFilterTest(TestCase):
    def setUp(self):
        for name, rc in [('a.pdf', 0), ('b.pdf', 3), ('c.pdf', 7)]:
            doc = Item.objects.create(
                name=name, status='COMPLETED', source=f'/tmp/{name}',
            )
            ItemData.objects.create(item=doc, payload={}, review_count=rc)
        self.fields = _make_fields()

    def test_equals(self):
        qs = Item.objects.all().select_related('data')
        fm = {'review_count': {'filterType': 'number', 'type': 'equals', 'filter': 3}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 1)

    def test_greater_than(self):
        qs = Item.objects.all().select_related('data')
        fm = {'review_count': {'filterType': 'number', 'type': 'greaterThan', 'filter': 2}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 2)

    def test_in_range(self):
        qs = Item.objects.all().select_related('data')
        fm = {'review_count': {'filterType': 'number', 'type': 'inRange', 'filter': 1, 'filterTo': 5}}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 1)


class CombinedFilterTest(TestCase):
    def setUp(self):
        for name in ['alpha.pdf', 'beta.pdf', 'gamma.pdf']:
            Item.objects.create(
                name=name, status='PENDING', source=f'/tmp/{name}',
            )
        self.fields = _make_fields()

    def test_or_combined(self):
        qs = Item.objects.all()
        fm = {'name': {
            'operator': 'OR',
            'condition1': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'},
            'condition2': {'filterType': 'text', 'type': 'contains', 'filter': 'gamma'},
        }}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 2)

    def test_and_combined(self):
        qs = Item.objects.all()
        fm = {'name': {
            'operator': 'AND',
            'condition1': {'filterType': 'text', 'type': 'startsWith', 'filter': 'a'},
            'condition2': {'filterType': 'text', 'type': 'endsWith', 'filter': 'a.pdf'},
        }}
        self.assertEqual(apply_filters(qs, fm, self.fields).count(), 1)


class SearchTest(TestCase):
    def setUp(self):
        for name, status in [('report.pdf', 'COMPLETED'), ('invoice.pdf', 'PENDING'), ('report_v2.pdf', 'FAILED')]:
            Item.objects.create(
                name=name, status=status, source=f'/tmp/{name}',
            )

    def test_search_matches_filename(self):
        qs = Item.objects.all()
        result = apply_search(qs, 'report', ['name', 'status'])
        self.assertEqual(result.count(), 2)

    def test_search_matches_status(self):
        qs = Item.objects.all()
        result = apply_search(qs, 'FAIL', ['name', 'status'])
        self.assertEqual(result.count(), 1)

    def test_empty_search_is_noop(self):
        qs = Item.objects.all()
        result = apply_search(qs, '', ['name', 'status'])
        self.assertEqual(result.count(), 3)
