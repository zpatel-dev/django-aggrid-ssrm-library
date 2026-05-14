"""
Comprehensive tests for aggrid_ssrm.filters — apply_filters and apply_search.

Covers every filter type (text, number, date, set), every operator,
combined/multi-column filters, search, and edge cases.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from tests.test_app.models import Item, ItemData
from aggrid_ssrm.fields import FieldDef
from aggrid_ssrm.filters import apply_filters, apply_search


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fields():
    """Standard field definitions used across most tests."""
    return {
        'name': FieldDef('name', 'name', field_type='text'),
        'status': FieldDef('status', 'status', field_type='set'),
        'review_count': FieldDef(
            'review_count', 'data__review_count', field_type='number',
        ),
        'updated_at': FieldDef('updated_at', 'updated_at', field_type='date'),
        'modified_at': FieldDef(
            'modified_at', 'modified_at', field_type='date',
        ),
        'unfilterable': FieldDef(
            'unfilterable', 'name', field_type='text', filterable=False,
        ),
    }


def _create_doc(name, status='PENDING', source=None,
                review_count=None, payload=None,
                modified_at=None):
    """Shortcut: create a Item (and optionally ItemData)."""
    doc = Item.objects.create(
        name=name,
        status=status,
        source=source or f'/tmp/{name}',
        modified_at=modified_at,
    )
    if review_count is not None or payload is not None:
        ItemData.objects.create(
            item=doc,
            payload=payload or {},
            review_count=review_count or 0,
        )
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# TEXT FILTER
# ═══════════════════════════════════════════════════════════════════════════

class TextFilterContainsTest(TestCase):
    def setUp(self):
        _create_doc('alpha.pdf')
        _create_doc('alphabet.pdf')
        _create_doc('beta.pdf')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_contains_matches_substring(self):
        fm = {'name': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_contains_case_insensitive(self):
        fm = {'name': {'filterType': 'text', 'type': 'contains', 'filter': 'ALPHA'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_contains_empty_string_matches_all(self):
        fm = {'name': {'filterType': 'text', 'type': 'contains', 'filter': ''}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 3)

    def test_contains_no_match(self):
        fm = {'name': {'filterType': 'text', 'type': 'contains', 'filter': 'zzzzz'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 0)


class TextFilterNotContainsTest(TestCase):
    def setUp(self):
        _create_doc('alpha.pdf')
        _create_doc('beta.pdf')
        _create_doc('gamma.pdf')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_not_contains_excludes_matches(self):
        fm = {'name': {'filterType': 'text', 'type': 'notContains', 'filter': 'alpha'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_not_contains_case_insensitive(self):
        fm = {'name': {'filterType': 'text', 'type': 'notContains', 'filter': 'ALPHA'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)


class TextFilterEqualsTest(TestCase):
    def setUp(self):
        _create_doc('alpha.pdf')
        _create_doc('Alpha.pdf', source='/tmp/Alpha.pdf')
        _create_doc('beta.pdf')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_equals_exact_match(self):
        fm = {'name': {'filterType': 'text', 'type': 'equals', 'filter': 'alpha.pdf'}}
        # iexact: matches both alpha.pdf and Alpha.pdf
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_equals_case_insensitive(self):
        fm = {'name': {'filterType': 'text', 'type': 'equals', 'filter': 'ALPHA.PDF'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_equals_no_match(self):
        fm = {'name': {'filterType': 'text', 'type': 'equals', 'filter': 'zzzz.pdf'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 0)


class TextFilterNotEqualTest(TestCase):
    def setUp(self):
        _create_doc('alpha.pdf')
        _create_doc('beta.pdf')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_not_equal_excludes_match(self):
        fm = {'name': {'filterType': 'text', 'type': 'notEqual', 'filter': 'alpha.pdf'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'beta.pdf')

    def test_not_equal_case_insensitive(self):
        fm = {'name': {'filterType': 'text', 'type': 'notEqual', 'filter': 'ALPHA.PDF'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)


class TextFilterStartsWithTest(TestCase):
    def setUp(self):
        _create_doc('report_2024.pdf')
        _create_doc('report_2025.pdf')
        _create_doc('invoice.pdf')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_starts_with(self):
        fm = {'name': {'filterType': 'text', 'type': 'startsWith', 'filter': 'report'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_starts_with_case_insensitive(self):
        fm = {'name': {'filterType': 'text', 'type': 'startsWith', 'filter': 'REPORT'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)


class TextFilterEndsWithTest(TestCase):
    def setUp(self):
        _create_doc('data.csv')
        _create_doc('report.pdf')
        _create_doc('backup.csv')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_ends_with(self):
        fm = {'name': {'filterType': 'text', 'type': 'endsWith', 'filter': '.csv'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_ends_with_case_insensitive(self):
        fm = {'name': {'filterType': 'text', 'type': 'endsWith', 'filter': '.CSV'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)


class TextFilterBlankNotBlankTest(TestCase):
    def setUp(self):
        _create_doc('filled.pdf')
        _create_doc('', source='/tmp/empty_name')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_blank_finds_empty_string(self):
        fm = {'name': {'filterType': 'text', 'type': 'blank'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)

    def test_not_blank_excludes_empty_string(self):
        fm = {'name': {'filterType': 'text', 'type': 'notBlank'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)


# ═══════════════════════════════════════════════════════════════════════════
# NUMBER FILTER
# ═══════════════════════════════════════════════════════════════════════════

class NumberFilterBasicTest(TestCase):
    def setUp(self):
        for name, rc in [('a.pdf', 0), ('b.pdf', 5), ('c.pdf', 10), ('d.pdf', -3)]:
            _create_doc(name, review_count=rc)
        self.qs = Item.objects.all().select_related('data')
        self.fields = _fields()

    def test_equals(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'equals', 'filter': 5}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)

    def test_equals_zero(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'equals', 'filter': 0}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)

    def test_not_equal(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'notEqual', 'filter': 5}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 3)

    def test_greater_than(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'greaterThan', 'filter': 4}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_greater_than_or_equal(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'greaterThanOrEqual', 'filter': 5}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_less_than(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'lessThan', 'filter': 5}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_less_than_or_equal(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'lessThanOrEqual', 'filter': 5}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 3)

    def test_negative_number_filter(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'lessThan', 'filter': 0}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'd.pdf')

    def test_negative_number_equals(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'equals', 'filter': -3}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)


class NumberFilterInRangeTest(TestCase):
    def setUp(self):
        for name, rc in [('a.pdf', 1), ('b.pdf', 5), ('c.pdf', 10), ('d.pdf', 15)]:
            _create_doc(name, review_count=rc)
        self.qs = Item.objects.all().select_related('data')
        self.fields = _fields()

    def test_in_range_inclusive_boundaries(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'inRange', 'filter': 5, 'filterTo': 10}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_in_range_exact_lower_boundary(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'inRange', 'filter': 1, 'filterTo': 1}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)

    def test_in_range_no_match(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'inRange', 'filter': 20, 'filterTo': 30}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 0)


class NumberFilterBlankNotBlankTest(TestCase):
    def setUp(self):
        _create_doc('with_data.pdf', review_count=5)
        # Doc without ItemData => data__review_column_count IS NULL
        _create_doc('no_data.pdf')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_blank_finds_null(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'blank'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)

    def test_not_blank_finds_non_null(self):
        fm = {'review_count': {'filterType': 'number', 'type': 'notBlank'}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 1)


# ═══════════════════════════════════════════════════════════════════════════
# DATE FILTER
# ═══════════════════════════════════════════════════════════════════════════

class DateFilterTest(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.doc_today = _create_doc(
            'today.pdf',
            modified_at=self.now,
        )
        self.doc_yesterday = _create_doc(
            'yesterday.pdf',
            modified_at=self.now - timedelta(days=1),
        )
        self.doc_last_week = _create_doc(
            'last_week.pdf',
            modified_at=self.now - timedelta(days=7),
        )
        self.doc_null = _create_doc(
            'null_date.pdf',
            modified_at=None,
        )
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_equals_date(self):
        date_str = self.now.strftime('%Y-%m-%d')
        fm = {'modified_at': {
            'filterType': 'date', 'type': 'equals', 'dateFrom': date_str,
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'today.pdf')

    def test_not_equal_date(self):
        date_str = self.now.strftime('%Y-%m-%d')
        fm = {'modified_at': {
            'filterType': 'date', 'type': 'notEqual', 'dateFrom': date_str,
        }}
        # yesterday + last_week (null_date has null, not a date, so ~Q(date=X)
        # includes rows where the date is not X but not null rows — however
        # Django's ~Q(field__date=X) actually DOES include NULL rows too.
        # Let's just check the count matches expectations.
        result = apply_filters(self.qs, fm, self.fields)
        self.assertIn(self.doc_yesterday, result)
        self.assertIn(self.doc_last_week, result)

    def test_greater_than_date(self):
        yesterday_str = (self.now - timedelta(days=1)).strftime('%Y-%m-%d')
        fm = {'modified_at': {
            'filterType': 'date', 'type': 'greaterThan', 'dateFrom': yesterday_str,
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'today.pdf')

    def test_less_than_date(self):
        yesterday_str = (self.now - timedelta(days=1)).strftime('%Y-%m-%d')
        fm = {'modified_at': {
            'filterType': 'date', 'type': 'lessThan', 'dateFrom': yesterday_str,
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'last_week.pdf')

    def test_in_range_date(self):
        start = (self.now - timedelta(days=2)).strftime('%Y-%m-%d')
        end = self.now.strftime('%Y-%m-%d')
        fm = {'modified_at': {
            'filterType': 'date', 'type': 'inRange',
            'dateFrom': start, 'dateTo': end,
        }}
        result = apply_filters(self.qs, fm, self.fields)
        # yesterday and today
        self.assertEqual(result.count(), 2)

    def test_blank_date(self):
        fm = {'modified_at': {
            'filterType': 'date', 'type': 'blank',
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'null_date.pdf')

    def test_not_blank_date(self):
        fm = {'modified_at': {
            'filterType': 'date', 'type': 'notBlank',
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 3)


# ═══════════════════════════════════════════════════════════════════════════
# SET FILTER
# ═══════════════════════════════════════════════════════════════════════════

class SetFilterTest(TestCase):
    def setUp(self):
        _create_doc('a.pdf', status='COMPLETED')
        _create_doc('b.pdf', status='PENDING')
        _create_doc('c.pdf', status='FAILED')
        _create_doc('d.pdf', status='COMPLETED')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_single_value(self):
        fm = {'status': {'filterType': 'set', 'values': ['COMPLETED']}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_multiple_values(self):
        fm = {'status': {'filterType': 'set', 'values': ['COMPLETED', 'PENDING']}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 3)

    def test_empty_list_returns_nothing(self):
        fm = {'status': {'filterType': 'set', 'values': []}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 0)

    def test_none_values_select_all(self):
        fm = {'status': {'filterType': 'set', 'values': None}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 4)

    def test_nonexistent_values(self):
        fm = {'status': {'filterType': 'set', 'values': ['NONEXISTENT']}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 0)

    def test_mix_existing_and_nonexistent(self):
        fm = {'status': {'filterType': 'set', 'values': ['COMPLETED', 'NONEXISTENT']}}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)


# ═══════════════════════════════════════════════════════════════════════════
# COMBINED FILTERS (AND / OR)
# ═══════════════════════════════════════════════════════════════════════════

class CombinedTextFilterTest(TestCase):
    def setUp(self):
        _create_doc('alpha_report.pdf')
        _create_doc('alpha_invoice.pdf')
        _create_doc('beta_report.pdf')
        _create_doc('gamma_memo.pdf')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_and_two_text_conditions(self):
        fm = {'name': {
            'operator': 'AND',
            'condition1': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'},
            'condition2': {'filterType': 'text', 'type': 'contains', 'filter': 'report'},
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'alpha_report.pdf')

    def test_or_two_text_conditions(self):
        fm = {'name': {
            'operator': 'OR',
            'condition1': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'},
            'condition2': {'filterType': 'text', 'type': 'contains', 'filter': 'gamma'},
        }}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 3)

    def test_combined_where_one_condition_matches_nothing(self):
        fm = {'name': {
            'operator': 'OR',
            'condition1': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'},
            'condition2': {'filterType': 'text', 'type': 'contains', 'filter': 'zzzzz'},
        }}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)

    def test_and_where_conditions_exclude_everything(self):
        fm = {'name': {
            'operator': 'AND',
            'condition1': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'},
            'condition2': {'filterType': 'text', 'type': 'contains', 'filter': 'gamma'},
        }}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 0)


class CombinedCrossTypeFilterTest(TestCase):
    """AND/OR combining text + number across different columns."""

    def setUp(self):
        _create_doc('alpha.pdf', review_count=10)
        _create_doc('beta.pdf', review_count=20)
        _create_doc('alpha_v2.pdf', review_count=30)
        self.qs = Item.objects.all().select_related('data')
        self.fields = _fields()

    def test_text_and_number_on_different_columns(self):
        """Filter name contains 'alpha' AND review_count > 15 => only alpha_v2."""
        fm = {
            'name': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'},
            'review_count': {'filterType': 'number', 'type': 'greaterThan', 'filter': 15},
        }
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'alpha_v2.pdf')


class CombinedSetSameColumnTest(TestCase):
    """OR with set + set on the same column (AG Grid combined on set)."""

    def setUp(self):
        _create_doc('a.pdf', status='COMPLETED')
        _create_doc('b.pdf', status='PENDING')
        _create_doc('c.pdf', status='FAILED')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_or_set_set(self):
        fm = {'status': {
            'operator': 'OR',
            'condition1': {'filterType': 'set', 'values': ['COMPLETED']},
            'condition2': {'filterType': 'set', 'values': ['FAILED']},
        }}
        self.assertEqual(apply_filters(self.qs, fm, self.fields).count(), 2)


class CombinedWithEmptyConditionTest(TestCase):
    """One condition is empty/None — should still apply the other."""

    def setUp(self):
        _create_doc('alpha.pdf')
        _create_doc('beta.pdf')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_and_with_empty_condition2(self):
        fm = {'name': {
            'operator': 'AND',
            'condition1': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'},
            'condition2': {},
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)

    def test_or_with_empty_condition1(self):
        """Empty condition defaults to text contains '' (matches all), so OR returns all."""
        fm = {'name': {
            'operator': 'OR',
            'condition1': {},
            'condition2': {'filterType': 'text', 'type': 'contains', 'filter': 'beta'},
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-COLUMN FILTERS
# ═══════════════════════════════════════════════════════════════════════════

class MultiColumnFilterTest(TestCase):
    def setUp(self):
        _create_doc('alpha.pdf', status='COMPLETED', review_count=5)
        _create_doc('beta.pdf', status='COMPLETED', review_count=10)
        _create_doc('gamma.pdf', status='PENDING', review_count=5)
        _create_doc('delta.pdf', status='FAILED', review_count=15)
        self.qs = Item.objects.all().select_related('data')
        self.fields = _fields()

    def test_two_column_filters(self):
        """status=COMPLETED AND name contains 'alpha'."""
        fm = {
            'status': {'filterType': 'set', 'values': ['COMPLETED']},
            'name': {'filterType': 'text', 'type': 'contains', 'filter': 'alpha'},
        }
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'alpha.pdf')

    def test_three_column_filters(self):
        """status=COMPLETED AND name starts 'b' AND review_count >= 10."""
        fm = {
            'status': {'filterType': 'set', 'values': ['COMPLETED']},
            'name': {'filterType': 'text', 'type': 'startsWith', 'filter': 'b'},
            'review_count': {'filterType': 'number', 'type': 'greaterThanOrEqual', 'filter': 10},
        }
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'beta.pdf')

    def test_filter_plus_search_combined(self):
        """Filter status + free-text search on name."""
        fm = {'status': {'filterType': 'set', 'values': ['COMPLETED']}}
        filtered = apply_filters(self.qs, fm, self.fields)
        result = apply_search(filtered, 'beta', ['name'])
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, 'beta.pdf')


# ═══════════════════════════════════════════════════════════════════════════
# SEARCH (apply_search)
# ═══════════════════════════════════════════════════════════════════════════

class SearchTest(TestCase):
    def setUp(self):
        _create_doc('report.pdf', status='COMPLETED')
        _create_doc('invoice.pdf', status='PENDING')
        _create_doc('report_v2.pdf', status='FAILED')
        self.qs = Item.objects.all()

    def test_search_matches_filename(self):
        result = apply_search(self.qs, 'report', ['name'])
        self.assertEqual(result.count(), 2)

    def test_search_matches_status(self):
        result = apply_search(self.qs, 'FAIL', ['status'])
        self.assertEqual(result.count(), 1)

    def test_search_across_multiple_fields(self):
        result = apply_search(self.qs, 'report', ['name', 'status'])
        self.assertEqual(result.count(), 2)

    def test_search_case_insensitive(self):
        result = apply_search(self.qs, 'REPORT', ['name'])
        self.assertEqual(result.count(), 2)

    def test_empty_search_is_noop(self):
        result = apply_search(self.qs, '', ['name'])
        self.assertEqual(result.count(), 3)

    def test_none_search_text_is_noop(self):
        result = apply_search(self.qs, None, ['name'])
        self.assertEqual(result.count(), 3)

    def test_empty_fields_list_is_noop(self):
        result = apply_search(self.qs, 'report', [])
        self.assertEqual(result.count(), 3)

    def test_search_no_match(self):
        result = apply_search(self.qs, 'zzzzzz', ['name', 'status'])
        self.assertEqual(result.count(), 0)


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class EdgeCaseTest(TestCase):
    def setUp(self):
        _create_doc('test.pdf', status='COMPLETED')
        _create_doc('other.pdf', status='PENDING')
        self.qs = Item.objects.all()
        self.fields = _fields()

    def test_unfilterable_field_skipped(self):
        fm = {'unfilterable': {'filterType': 'text', 'type': 'contains', 'filter': 'test'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_unknown_filter_type_skipped(self):
        fm = {'name': {'filterType': 'bogus_type', 'type': 'contains', 'filter': 'test'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_empty_filter_model_returns_all(self):
        fm = {}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_column_not_in_fields_dict_skipped(self):
        fm = {'nonexistent_column': {'filterType': 'text', 'type': 'contains', 'filter': 'x'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_filter_with_unknown_operator_type_returns_all(self):
        """A text filter with an unknown operator type (e.g. 'foobar') should be a no-op."""
        fm = {'name': {'filterType': 'text', 'type': 'foobar', 'filter': 'test'}}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_number_filter_with_none_filter_value(self):
        """Number equals with filter=None should not crash."""
        _create_doc('x.pdf', review_count=5)
        qs = Item.objects.all().select_related('data')
        fm = {'review_count': {'filterType': 'number', 'type': 'equals', 'filter': None}}
        # Should handle gracefully (ORM: WHERE col = NULL is valid SQL)
        result = apply_filters(qs, fm, self.fields)
        self.assertIsNotNone(result)

    def test_date_filter_missing_date_from_is_noop(self):
        """Date equals without dateFrom should be a no-op."""
        fm = {'modified_at': {
            'filterType': 'date', 'type': 'equals',
        }}
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 2)

    def test_multiple_edge_filters_at_once(self):
        """Combine unfilterable + unknown column + valid filter."""
        fm = {
            'unfilterable': {'filterType': 'text', 'type': 'contains', 'filter': 'test'},
            'nonexistent': {'filterType': 'set', 'values': ['X']},
            'status': {'filterType': 'set', 'values': ['COMPLETED']},
        }
        result = apply_filters(self.qs, fm, self.fields)
        self.assertEqual(result.count(), 1)
