"""
Comprehensive tests for aggrid_ssrm.grouping — handle_grouped_request.

Covers direct field grouping, JSON field grouping, multi-level grouping,
grouping with filters active, value column aggregation, and edge cases.
"""
from django.test import TestCase

from tests.test_app.models import Item, ItemData
from aggrid_ssrm import FieldDef, SSRMConfig, SSRMRequest, process_ssrm_request
from aggrid_ssrm.grouping import handle_grouped_request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_builder(instance, field_defs):
    """Simple row builder that uses value_getter or getattr."""
    row = {}
    for fd in field_defs:
        if fd.value_getter:
            row[fd.col_id] = fd.value_getter(instance)
        else:
            row[fd.col_id] = getattr(instance, fd.col_id, None)
    return row


def _vg(col):
    """Value getter factory for top-level payload keys."""
    def getter(d):
        ed = d.data.payload if hasattr(d, 'data') else {}
        return ed.get(col) if isinstance(ed, dict) else None
    return getter


# ---------------------------------------------------------------------------
# Shared setUp data
# ---------------------------------------------------------------------------

STATES = ['TX', 'CA', 'OK']
COUNTIES = ['Travis', 'Harris', 'Los Angeles', 'Tulsa', 'Dallas']


def _build_fields():
    """Standard field definitions for grouping tests."""
    return [
        FieldDef('name', 'name'),
        FieldDef('status', 'status', field_type='set'),
        FieldDef('review_count', 'data__review_count', field_type='number',
                 value_getter=lambda d: d.data.review_count if hasattr(d, 'data') else 0),
        FieldDef('state', 'data__payload__state', is_json=True,
                 value_getter=_vg('state')),
        FieldDef('amount', 'data__payload__amount', is_json=True,
                 field_type='number', value_getter=_vg('amount')),
        FieldDef('county', 'data__payload__county', is_json=True,
                 value_getter=_vg('county')),
    ]


def _build_fields_dict(field_defs):
    return {fd.col_id: fd for fd in field_defs}


class _GroupingTestBase(TestCase):
    """
    Base class that creates a project with 20 documents:
    COMPLETED x8, PENDING x6, FAILED x4, CONVERTING x2.
    Each doc has payload with state, amount, county.
    """

    def setUp(self):
        statuses = (
            ['COMPLETED'] * 8
            + ['PENDING'] * 6
            + ['FAILED'] * 4
            + ['CONVERTING'] * 2
        )
        for i, status in enumerate(statuses):
            doc = Item.objects.create(
                name=f'doc{i:02d}.pdf',
                status=status,
                source=f'/tmp/doc{i:02d}.pdf',
            )
            ItemData.objects.create(
                item=doc,
                payload={
                    'state': STATES[i % len(STATES)],
                    'amount': (i + 1) * 100,
                    'county': COUNTIES[i % len(COUNTIES)],
                },
                review_count=i % 5,
            )

        self.field_defs = _build_fields()
        self.fields_dict = _build_fields_dict(self.field_defs)
        self.config = SSRMConfig(
            fields=self.field_defs,
            default_sort=['-pk'],
            search_fields=['name', 'status'],
        )

    def _qs(self):
        return Item.objects.all().select_related('data')

    def _grouped(self, row_group_cols, group_keys, start=0, end=100,
                 filter_model=None, sort_model=None, value_cols=None,
                 extra=None):
        """Convenience to run handle_grouped_request."""
        body = {
            'startRow': start,
            'endRow': end,
            'rowGroupCols': row_group_cols,
            'groupKeys': group_keys,
        }
        if filter_model:
            body['filterModel'] = filter_model
        if sort_model:
            body['sortModel'] = sort_model
        if value_cols:
            body['valueCols'] = value_cols
        if extra:
            body.update(extra)
        req = SSRMRequest.from_body(body)
        return handle_grouped_request(
            self._qs(), req, self.fields_dict, _row_builder,
            self.field_defs, ['-pk'],
        )

    def _process(self, body):
        """Convenience to run process_ssrm_request with full config."""
        req = SSRMRequest.from_body(body)
        return process_ssrm_request(self.config, req, self._qs())


# ===========================================================================
# DIRECT FIELD GROUPING
# ===========================================================================

class DirectFieldGroupCountTest(_GroupingTestBase):
    def test_group_by_status_returns_four_groups(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
        )
        self.assertEqual(result['rowCount'], 4)


class DirectFieldGroupChildCountTest(_GroupingTestBase):
    def test_completed_child_count_is_8(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
        )
        counts = {r['status']: r['childCount'] for r in result['rowData']}
        self.assertEqual(counts['COMPLETED'], 8)

    def test_pending_child_count_is_6(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
        )
        counts = {r['status']: r['childCount'] for r in result['rowData']}
        self.assertEqual(counts['PENDING'], 6)

    def test_failed_child_count_is_4(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
        )
        counts = {r['status']: r['childCount'] for r in result['rowData']}
        self.assertEqual(counts['FAILED'], 4)

    def test_converting_child_count_is_2(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
        )
        counts = {r['status']: r['childCount'] for r in result['rowData']}
        self.assertEqual(counts['CONVERTING'], 2)


class DirectFieldGroupRowShapeTest(_GroupingTestBase):
    def test_group_rows_have_status_field(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
        )
        for row in result['rowData']:
            self.assertIn('status', row)

    def test_group_rows_have_child_count_field(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
        )
        for row in result['rowData']:
            self.assertIn('childCount', row)


class DirectFieldGroupSortTest(_GroupingTestBase):
    def test_groups_sorted_alphabetically(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
        )
        statuses = [r['status'] for r in result['rowData']]
        self.assertEqual(statuses, sorted(statuses))


class DirectFieldGroupPaginationTest(_GroupingTestBase):
    def test_group_pagination_page_1(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
            start=0, end=2,
        )
        self.assertEqual(len(result['rowData']), 2)
        self.assertEqual(result['rowCount'], 4)

    def test_group_pagination_page_2(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
            start=2, end=4,
        )
        self.assertEqual(len(result['rowData']), 2)
        self.assertEqual(result['rowCount'], 4)


class DrillDownCompletedTest(_GroupingTestBase):
    def test_drill_into_completed_returns_8_leaf_rows(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}],
            ['COMPLETED'],
        )
        self.assertEqual(result['rowCount'], 8)


class DrillDownFailedTest(_GroupingTestBase):
    def test_drill_into_failed_returns_4_leaf_rows(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}],
            ['FAILED'],
        )
        self.assertEqual(result['rowCount'], 4)


class DrillDownLeafRowShapeTest(_GroupingTestBase):
    def test_leaf_rows_have_filename(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}],
            ['COMPLETED'],
        )
        for row in result['rowData']:
            self.assertIn('name', row)

    def test_leaf_rows_have_status(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}],
            ['COMPLETED'],
        )
        for row in result['rowData']:
            self.assertIn('status', row)

    def test_leaf_rows_have_extracted_columns(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}],
            ['COMPLETED'],
        )
        for row in result['rowData']:
            self.assertIn('state', row)
            self.assertIn('amount', row)


class DrillDownDefaultSortTest(_GroupingTestBase):
    def test_leaf_rows_sorted_by_default_sort(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}],
            ['COMPLETED'],
        )
        # default_sort is ['-pk'] => descending pk => IDs should be decreasing
        ids = [r.get('name') for r in result['rowData']]
        # filenames are doc00..doc19, sorted desc by pk means highest doc numbers first
        self.assertEqual(ids, sorted(ids, reverse=True))


# ===========================================================================
# JSON FIELD GROUPING (top-level, not array)
# ===========================================================================

class JsonFieldGroupStateTest(_GroupingTestBase):
    def test_group_by_state_returns_3_groups(self):
        result = self._grouped(
            [{'field': 'state', 'colId': 'state'}], [],
        )
        self.assertEqual(result['rowCount'], 3)

    def test_group_by_state_child_counts_add_to_total(self):
        result = self._grouped(
            [{'field': 'state', 'colId': 'state'}], [],
        )
        total = sum(r['childCount'] for r in result['rowData'])
        self.assertEqual(total, 20)

    def test_group_by_state_then_drill_into_tx(self):
        result = self._grouped(
            [{'field': 'state', 'colId': 'state'}],
            ['TX'],
        )
        # TX assigned to indices 0,3,6,9,12,15,18 => 7 docs
        self.assertEqual(result['rowCount'], 7)


class JsonFieldGroupAmountTest(_GroupingTestBase):
    def test_group_by_amount_returns_many_unique_values(self):
        result = self._grouped(
            [{'field': 'amount', 'colId': 'amount'}], [],
        )
        # Each doc has a unique amount (100, 200, ..., 2000) => 20 groups
        self.assertEqual(result['rowCount'], 20)


# ===========================================================================
# MULTI-LEVEL GROUPING
# ===========================================================================

class MultiLevelGroupStatusStatTest(_GroupingTestBase):
    def test_first_level_shows_status_groups(self):
        result = self._grouped(
            [
                {'field': 'status', 'colId': 'status'},
                {'field': 'state', 'colId': 'state'},
            ],
            [],
        )
        self.assertEqual(result['rowCount'], 4)

    def test_drill_into_completed_shows_state_sub_groups(self):
        result = self._grouped(
            [
                {'field': 'status', 'colId': 'status'},
                {'field': 'state', 'colId': 'state'},
            ],
            ['COMPLETED'],
        )
        # COMPLETED docs are at indices 0..7, states cycle TX/CA/OK
        # 0:TX, 1:CA, 2:OK, 3:TX, 4:CA, 5:OK, 6:TX, 7:CA => 3 states
        self.assertEqual(result['rowCount'], 3)

    def test_drill_into_completed_then_tx_shows_leaf_rows(self):
        result = self._grouped(
            [
                {'field': 'status', 'colId': 'status'},
                {'field': 'state', 'colId': 'state'},
            ],
            ['COMPLETED', 'TX'],
        )
        # COMPLETED + TX: indices 0, 3, 6 => 3 docs
        self.assertEqual(result['rowCount'], 3)
        for row in result['rowData']:
            self.assertIn('name', row)


class MultiLevelGroupStateStatusTest(_GroupingTestBase):
    def test_different_order_first_level_shows_state_groups(self):
        result = self._grouped(
            [
                {'field': 'state', 'colId': 'state'},
                {'field': 'status', 'colId': 'status'},
            ],
            [],
        )
        self.assertEqual(result['rowCount'], 3)


# ===========================================================================
# GROUPING WITH FILTERS ACTIVE
# ===========================================================================

class GroupWithSetFilterTest(_GroupingTestBase):
    def test_group_by_status_with_state_filter_tx(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'rowGroupCols': [{'field': 'status', 'colId': 'status'}],
            'groupKeys': [],
            'filterModel': {
                'state': {'filterType': 'set', 'values': ['TX']},
            },
        })
        # TX docs at indices 0,3,6,9,12,15,18
        # statuses: COMPLETED(0,3,6), PENDING(9,12), FAILED(15,18) => 3 groups
        # (no CONVERTING among TX docs)
        total_children = sum(r['childCount'] for r in result['rowData'])
        self.assertEqual(total_children, 7)


class GroupWithSearchTest(_GroupingTestBase):
    def test_group_by_state_with_search_on_filename(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'rowGroupCols': [{'field': 'state', 'colId': 'state'}],
            'groupKeys': [],
            'search': 'doc01',
        })
        # Only doc01.pdf matches, which is in state CA
        total_children = sum(r['childCount'] for r in result['rowData'])
        self.assertEqual(total_children, 1)


class GroupWithNumberFilterTest(_GroupingTestBase):
    def test_group_by_status_with_amount_gt_500(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'rowGroupCols': [{'field': 'status', 'colId': 'status'}],
            'groupKeys': [],
            'filterModel': {
                'amount': {'filterType': 'number', 'type': 'greaterThan', 'filter': 500},
            },
        })
        # amount > 500 => indices 5..19 (amounts 600..2000) => 15 docs
        total_children = sum(r['childCount'] for r in result['rowData'])
        self.assertEqual(total_children, 15)


# ===========================================================================
# GROUPING WITH VALUE AGGREGATION
# ===========================================================================

class AggSumTest(_GroupingTestBase):
    def test_sum_review_count_by_status(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
            value_cols=[{'field': 'review_count', 'aggFunc': 'sum'}],
        )
        for row in result['rowData']:
            self.assertIn('review_count', row)


class AggAvgTest(_GroupingTestBase):
    def test_avg_review_count_by_status(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
            value_cols=[{'field': 'review_count', 'aggFunc': 'avg'}],
        )
        for row in result['rowData']:
            self.assertIn('review_count', row)


class AggCountTest(_GroupingTestBase):
    def test_count_review_count_by_status(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
            value_cols=[{'field': 'review_count', 'aggFunc': 'count'}],
        )
        for row in result['rowData']:
            self.assertIn('review_count', row)


class AggMinTest(_GroupingTestBase):
    def test_min_review_count_by_status(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
            value_cols=[{'field': 'review_count', 'aggFunc': 'min'}],
        )
        for row in result['rowData']:
            self.assertIn('review_count', row)


class AggMaxTest(_GroupingTestBase):
    def test_max_review_count_by_status(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
            value_cols=[{'field': 'review_count', 'aggFunc': 'max'}],
        )
        for row in result['rowData']:
            self.assertIn('review_count', row)


# ===========================================================================
# EDGE CASES
# ===========================================================================

class GroupEmptyQuerysetTest(TestCase):
    def test_group_on_empty_queryset_returns_empty(self):
        field_defs = _build_fields()
        fields_dict = _build_fields_dict(field_defs)
        req = SSRMRequest(
            row_group_cols=[{'field': 'status', 'colId': 'status'}],
            group_keys=[], start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, fields_dict, _row_builder, field_defs, ['-pk'],
        )
        self.assertEqual(result['rowData'], [])
        self.assertEqual(result['rowCount'], 0)


class GroupAllSameValueTest(TestCase):
    def test_group_on_field_all_same_returns_one_group(self):
        for i in range(5):
            doc = Item.objects.create(
                name=f'f{i}.pdf',
                status='COMPLETED', source=f'/tmp/f{i}.pdf',
            )
            ItemData.objects.create(
                item=doc, payload={'state': 'TX'},
            )
        field_defs = _build_fields()
        fields_dict = _build_fields_dict(field_defs)
        req = SSRMRequest(
            row_group_cols=[{'field': 'status', 'colId': 'status'}],
            group_keys=[], start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, fields_dict, _row_builder, field_defs, ['-pk'],
        )
        self.assertEqual(result['rowCount'], 1)


class GroupAllUniqueValuesTest(TestCase):
    def test_group_on_field_all_unique_returns_n_groups(self):
        for i in range(5):
            doc = Item.objects.create(
                name=f'file{i}.pdf',
                status=['COMPLETED', 'PENDING', 'FAILED', 'CONVERTING', 'EXTRACTION_FAILED'][i],
                source=f'/tmp/file{i}.pdf',
            )
            ItemData.objects.create(
                item=doc, payload={'state': 'TX'},
            )
        field_defs = _build_fields()
        fields_dict = _build_fields_dict(field_defs)
        req = SSRMRequest(
            row_group_cols=[{'field': 'status', 'colId': 'status'}],
            group_keys=[], start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, fields_dict, _row_builder, field_defs, ['-pk'],
        )
        self.assertEqual(result['rowCount'], 5)


class GroupByUnknownFieldTest(_GroupingTestBase):
    def test_group_by_unknown_field_returns_empty(self):
        result = self._grouped(
            [{'field': 'nonexistent', 'colId': 'nonexistent'}], [],
        )
        self.assertEqual(result['rowData'], [])
        self.assertEqual(result['rowCount'], 0)


class GroupByNonGroupableFieldTest(TestCase):
    def test_group_by_non_groupable_field_returns_empty(self):
        doc = Item.objects.create(
            name='a.pdf',
            status='COMPLETED', source='/tmp/a.pdf',
        )
        ItemData.objects.create(item=doc, payload={})
        field_defs = [
            FieldDef('name', 'name', groupable=False),
            FieldDef('status', 'status', field_type='set'),
        ]
        fields_dict = {fd.col_id: fd for fd in field_defs}
        req = SSRMRequest(
            row_group_cols=[{'field': 'name', 'colId': 'name'}],
            group_keys=[], start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, fields_dict, _row_builder, field_defs, ['-pk'],
        )
        self.assertEqual(result['rowData'], [])
        self.assertEqual(result['rowCount'], 0)


class GroupPaginationSkipFirstTest(_GroupingTestBase):
    def test_start_row_1_skips_first_group(self):
        result = self._grouped(
            [{'field': 'status', 'colId': 'status'}], [],
            start=1, end=100,
        )
        # 4 total groups, skipping first => 3 returned
        self.assertEqual(len(result['rowData']), 3)
        self.assertEqual(result['rowCount'], 4)
