"""
Comprehensive tests for aggrid_ssrm.engine — process_ssrm_request,
default_row_builder, _resolve_orm_path, row_expander, SSRMRequest, SSRMConfig.

Covers flat pagination, sorting, search, row builder, row expander,
SSRMRequest parsing, and SSRMConfig behaviour.
"""
from django.test import TestCase

from tests.test_app.models import Item, ItemData
from aggrid_ssrm import (
    FieldDef, SSRMConfig, SSRMRequest,
    default_row_builder, process_ssrm_request,
)
from aggrid_ssrm.engine import _resolve_orm_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vg(col):
    """Value getter factory for top-level payload keys."""
    def getter(d):
        ed = d.data.payload if hasattr(d, 'data') else {}
        return ed.get(col) if isinstance(ed, dict) else None
    return getter


def _make_config(**overrides):
    """Build a standard SSRMConfig with optional overrides."""
    defaults = dict(
        fields=[
            FieldDef('name', 'name'),
            FieldDef('status', 'status', field_type='set'),
            FieldDef('review_count', 'data__review_count', field_type='number',
                     value_getter=lambda d: d.data.review_count if hasattr(d, 'data') else 0),
            FieldDef('state', 'data__payload__state', is_json=True,
                     value_getter=_vg('state')),
        ],
        default_sort=['-pk'],
        search_fields=['name', 'status'],
    )
    defaults.update(overrides)
    return SSRMConfig(**defaults)


# ===========================================================================
# FLAT PAGINATION
# ===========================================================================

class _FlatPaginationBase(TestCase):
    def setUp(self):
        for i in range(15):
            doc = Item.objects.create(
                name=f'doc{i:02d}.pdf',
                status='COMPLETED' if i % 2 == 0 else 'PENDING',
                source=f'/tmp/doc{i:02d}.pdf',
            )
            ItemData.objects.create(
                item=doc,
                payload={'state': ['TX', 'CA', 'OK'][i % 3]},
                review_count=i,
            )
        self.config = _make_config()

    def _qs(self):
        return Item.objects.all().select_related('data')

    def _process(self, body):
        req = SSRMRequest.from_body(body)
        return process_ssrm_request(self.config, req, self._qs())


class FlatStartEndZeroTest(_FlatPaginationBase):
    def test_start_0_end_0_returns_0_rows(self):
        result = self._process({'startRow': 0, 'endRow': 0})
        self.assertEqual(len(result['rowData']), 0)

    def test_start_0_end_0_returns_correct_total(self):
        result = self._process({'startRow': 0, 'endRow': 0})
        self.assertEqual(result['rowCount'], 15)


class FlatStartBeyondTotalTest(_FlatPaginationBase):
    def test_start_beyond_total_returns_0_rows(self):
        result = self._process({'startRow': 100, 'endRow': 200})
        self.assertEqual(len(result['rowData']), 0)

    def test_start_beyond_total_returns_correct_total(self):
        result = self._process({'startRow': 100, 'endRow': 200})
        self.assertEqual(result['rowCount'], 15)


class FlatStartEqualsEndTest(_FlatPaginationBase):
    def test_start_equals_end_returns_0_rows(self):
        result = self._process({'startRow': 5, 'endRow': 5})
        self.assertEqual(len(result['rowData']), 0)


class FlatExactFillTest(_FlatPaginationBase):
    def test_end_row_equals_total(self):
        result = self._process({'startRow': 0, 'endRow': 15})
        self.assertEqual(len(result['rowData']), 15)


class FlatPageSize1Test(_FlatPaginationBase):
    def test_page_size_1_returns_exactly_1_row(self):
        result = self._process({'startRow': 0, 'endRow': 1})
        self.assertEqual(len(result['rowData']), 1)


class FlatDefaultSortTest(_FlatPaginationBase):
    def test_default_sort_applied_when_no_sort_model(self):
        result = self._process({'startRow': 0, 'endRow': 15})
        # default_sort is ['-pk'] so rows should be in descending pk order
        filenames = [r['name'] for r in result['rowData']]
        self.assertEqual(filenames, sorted(filenames, reverse=True))


class FlatNoPaginationOverlapTest(_FlatPaginationBase):
    def test_sequential_pages_no_overlap(self):
        r1 = self._process({'startRow': 0, 'endRow': 5})
        r2 = self._process({'startRow': 5, 'endRow': 10})
        r3 = self._process({'startRow': 10, 'endRow': 15})
        names1 = [r['name'] for r in r1['rowData']]
        names2 = [r['name'] for r in r2['rowData']]
        names3 = [r['name'] for r in r3['rowData']]
        all_names = names1 + names2 + names3
        self.assertEqual(len(all_names), len(set(all_names)))


# ===========================================================================
# SORTING
# ===========================================================================

class _SortBase(TestCase):
    def setUp(self):
        for i, (name, status) in enumerate([
            ('charlie.pdf', 'PENDING'),
            ('alpha.pdf', 'COMPLETED'),
            ('bravo.pdf', 'FAILED'),
            ('delta.pdf', 'COMPLETED'),
        ]):
            doc = Item.objects.create(
                name=name,
                status=status, source=f'/tmp/{name}',
            )
            ItemData.objects.create(
                item=doc,
                payload={'state': ['TX', 'CA', 'OK', 'TX'][i]},
                review_count=i,
            )
        self.config = _make_config()

    def _qs(self):
        return Item.objects.all().select_related('data')

    def _process(self, body):
        req = SSRMRequest.from_body(body)
        return process_ssrm_request(self.config, req, self._qs())


class SortFilenameAscTest(_SortBase):
    def test_sort_by_filename_asc(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'sortModel': [{'colId': 'name', 'sort': 'asc'}],
        })
        filenames = [r['name'] for r in result['rowData']]
        self.assertEqual(filenames, sorted(filenames))


class SortFilenameDescTest(_SortBase):
    def test_sort_by_filename_desc(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'sortModel': [{'colId': 'name', 'sort': 'desc'}],
        })
        filenames = [r['name'] for r in result['rowData']]
        self.assertEqual(filenames, sorted(filenames, reverse=True))


class SortMultiColumnTest(_SortBase):
    def test_sort_by_status_then_filename(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'sortModel': [
                {'colId': 'status', 'sort': 'asc'},
                {'colId': 'name', 'sort': 'asc'},
            ],
        })
        rows = result['rowData']
        pairs = [(r['status'], r['name']) for r in rows]
        self.assertEqual(pairs, sorted(pairs))


class SortByJsonFieldTest(_SortBase):
    def test_sort_by_json_state_field(self):
        # state uses orm_path 'data__payload__state' — will sort by
        # the raw JSON key ordering in SQLite
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'sortModel': [{'colId': 'state', 'sort': 'asc'}],
        })
        # Just verify it doesn't crash and returns all rows
        self.assertEqual(len(result['rowData']), 4)


# ===========================================================================
# SEARCH
# ===========================================================================

class _SearchBase(TestCase):
    def setUp(self):
        for i, (name, status) in enumerate([
            ('report_q1.pdf', 'COMPLETED'),
            ('report_q2.pdf', 'PENDING'),
            ('invoice_001.pdf', 'FAILED'),
            ('invoice_002.pdf', 'COMPLETED'),
            ('memo.pdf', 'PENDING'),
        ]):
            doc = Item.objects.create(
                name=name,
                status=status, source=f'/tmp/{name}',
            )
            ItemData.objects.create(
                item=doc,
                payload={'state': 'TX'},
                review_count=i,
            )
        self.config = _make_config()

    def _qs(self):
        return Item.objects.all().select_related('data')

    def _process(self, body):
        req = SSRMRequest.from_body(body)
        return process_ssrm_request(self.config, req, self._qs())


class SearchMatchesFilenameTest(_SearchBase):
    def test_search_matches_filename_substring(self):
        result = self._process({
            'startRow': 0, 'endRow': 100, 'search': 'report',
        })
        self.assertEqual(result['rowCount'], 2)


class SearchMatchesStatusTest(_SearchBase):
    def test_search_matches_status_substring(self):
        result = self._process({
            'startRow': 0, 'endRow': 100, 'search': 'FAIL',
        })
        self.assertEqual(result['rowCount'], 1)


class SearchCaseInsensitiveTest(_SearchBase):
    def test_search_case_insensitive(self):
        result = self._process({
            'startRow': 0, 'endRow': 100, 'search': 'REPORT',
        })
        self.assertEqual(result['rowCount'], 2)


class SearchNoMatchTest(_SearchBase):
    def test_search_no_matches_returns_0(self):
        result = self._process({
            'startRow': 0, 'endRow': 100, 'search': 'zzzznonexistent',
        })
        self.assertEqual(result['rowCount'], 0)


class SearchEmptyStringTest(_SearchBase):
    def test_search_empty_string_returns_all(self):
        result = self._process({
            'startRow': 0, 'endRow': 100, 'search': '',
        })
        self.assertEqual(result['rowCount'], 5)


class SearchPlusFilterTest(_SearchBase):
    def test_search_and_filter_combined(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'search': 'report',
            'filterModel': {'status': {'filterType': 'set', 'values': ['COMPLETED']}},
        })
        self.assertEqual(result['rowCount'], 1)


class SearchPlusSortTest(_SearchBase):
    def test_search_and_sort_combined(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'search': 'invoice',
            'sortModel': [{'colId': 'name', 'sort': 'asc'}],
        })
        filenames = [r['name'] for r in result['rowData']]
        self.assertEqual(filenames, sorted(filenames))
        self.assertEqual(result['rowCount'], 2)


class SearchPlusPaginationTest(_SearchBase):
    def test_search_plus_pagination(self):
        result = self._process({
            'startRow': 0, 'endRow': 1, 'search': 'invoice',
        })
        self.assertEqual(len(result['rowData']), 1)
        self.assertEqual(result['rowCount'], 2)


# ===========================================================================
# ROW BUILDER
# ===========================================================================

class DefaultRowBuilderDirectFieldTest(TestCase):
    def setUp(self):
        doc = Item.objects.create(
            name='test.pdf',
            status='COMPLETED', source='/tmp/test.pdf',
        )
        ItemData.objects.create(
            item=doc, payload={'state': 'TX'},
            review_count=5,
        )
        self.doc = Item.objects.select_related('data').get(pk=doc.pk)

    def test_resolves_direct_fields(self):
        fields = [FieldDef('name', 'name')]
        row = default_row_builder(self.doc, fields)
        self.assertEqual(row['name'], 'test.pdf')


class DefaultRowBuilderRelatedFieldTest(TestCase):
    def setUp(self):
        doc = Item.objects.create(
            name='test.pdf',
            status='COMPLETED', source='/tmp/test.pdf',
        )
        ItemData.objects.create(
            item=doc, payload={}, review_count=7,
        )
        self.doc = Item.objects.select_related('data').get(pk=doc.pk)

    def test_resolves_related_fields(self):
        fields = [FieldDef('review_count', 'data__review_count')]
        row = default_row_builder(self.doc, fields)
        self.assertEqual(row['review_count'], 7)


class DefaultRowBuilderJsonFieldTest(TestCase):
    def setUp(self):
        doc = Item.objects.create(
            name='test.pdf',
            status='COMPLETED', source='/tmp/test.pdf',
        )
        ItemData.objects.create(
            item=doc, payload={'state': 'TX', 'county': 'Travis'},
        )
        self.doc = Item.objects.select_related('data').get(pk=doc.pk)

    def test_resolves_json_fields(self):
        fields = [FieldDef('state', 'data__payload__state', is_json=True)]
        row = default_row_builder(self.doc, fields)
        self.assertEqual(row['state'], 'TX')


class DefaultRowBuilderMissingRelationTest(TestCase):
    def setUp(self):
        # Item without ItemData
        self.doc = Item.objects.create(
            name='orphan.pdf',
            status='PENDING', source='/tmp/orphan.pdf',
        )

    def test_returns_none_for_missing_relation(self):
        fields = [FieldDef('review_count', 'data__review_count')]
        row = default_row_builder(self.doc, fields)
        self.assertIsNone(row['review_count'])


class CustomRowBuilderTest(TestCase):
    def setUp(self):
        doc = Item.objects.create(
            name='custom.pdf',
            status='COMPLETED', source='/tmp/custom.pdf',
        )
        ItemData.objects.create(item=doc, payload={})
        self.doc = Item.objects.select_related('data').get(pk=doc.pk)

    def test_custom_row_builder_used(self):
        def custom_builder(instance, field_defs):
            return {'custom_key': 'custom_value', 'name': instance.name}

        config = SSRMConfig(
            fields=[FieldDef('name', 'name')],
            row_builder=custom_builder,
        )
        req = SSRMRequest(start_row=0, end_row=10)
        qs = Item.objects.filter(pk=self.doc.pk).select_related('data')
        result = process_ssrm_request(config, req, qs)
        self.assertEqual(result['rowData'][0]['custom_key'], 'custom_value')


class ResolveOrmPathDeeplyNestedTest(TestCase):
    def test_deeply_nested_path(self):
        class Inner:
            value = 42
        class Middle:
            inner = Inner()
        class Outer:
            middle = Middle()
        result = _resolve_orm_path(Outer(), 'middle__inner__value')
        self.assertEqual(result, 42)


# ===========================================================================
# ROW EXPANDER
# ===========================================================================

class _ExpanderBase(TestCase):
    def setUp(self):
        # Doc with 3 items
        doc1 = Item.objects.create(
            name='multi.pdf',
            status='COMPLETED', source='/tmp/multi.pdf',
        )
        ItemData.objects.create(
            item=doc1,
            payload={'items': [
                {'tract': 'T1', 'acres': 10},
                {'tract': 'T2', 'acres': 20},
                {'tract': 'T3', 'acres': 30},
            ]},
        )
        # Doc with 1 item
        doc2 = Item.objects.create(
            name='single.pdf',
            status='COMPLETED', source='/tmp/single.pdf',
        )
        ItemData.objects.create(
            item=doc2,
            payload={'items': [{'tract': 'T4', 'acres': 40}]},
        )
        # Doc with 0 items
        doc3 = Item.objects.create(
            name='empty.pdf',
            status='PENDING', source='/tmp/empty.pdf',
        )
        ItemData.objects.create(
            item=doc3, payload={'note': 'no items'},
        )

        def _expander(instance, field_defs):
            base = {}
            for fd in field_defs:
                if fd.value_getter:
                    base[fd.col_id] = fd.value_getter(instance)
                else:
                    base[fd.col_id] = getattr(instance, fd.col_id, None)
            extracted = instance.data.payload if hasattr(instance, 'data') else {}
            items = extracted.get('items', []) if isinstance(extracted, dict) else []
            if not items:
                return [base]
            json_cols = [fd.col_id for fd in field_defs if fd.is_json]
            rows = []
            for item in items:
                row = {**base}
                for col in json_cols:
                    if isinstance(item, dict) and col in item:
                        row[col] = item[col]
                rows.append(row)
            return rows

        self.config = SSRMConfig(
            fields=[
                FieldDef('name', 'name'),
                FieldDef('status', 'status', field_type='set'),
                FieldDef('tract', 'data__payload__tract',
                         is_json=True, value_getter=_vg('tract')),
                FieldDef('acres', 'data__payload__acres',
                         is_json=True, field_type='number', value_getter=_vg('acres')),
            ],
            row_expander=_expander,
            default_sort=['name'],
            search_fields=['name', 'status'],
        )

    def _qs(self):
        return Item.objects.all().select_related('data')

    def _process(self, body):
        req = SSRMRequest.from_body(body)
        return process_ssrm_request(self.config, req, self._qs())


class ExpanderZeroItemsTest(_ExpanderBase):
    def test_zero_items_produces_1_row(self):
        qs = Item.objects.filter(
            name='empty.pdf',
        ).select_related('data')
        req = SSRMRequest(start_row=0, end_row=100)
        result = process_ssrm_request(self.config, req, qs)
        self.assertEqual(result['rowCount'], 1)


class ExpanderOneItemTest(_ExpanderBase):
    def test_one_item_produces_1_row(self):
        qs = Item.objects.filter(
            name='single.pdf',
        ).select_related('data')
        req = SSRMRequest(start_row=0, end_row=100)
        result = process_ssrm_request(self.config, req, qs)
        self.assertEqual(result['rowCount'], 1)


class ExpanderNItemsTest(_ExpanderBase):
    def test_n_items_produces_n_rows(self):
        qs = Item.objects.filter(
            name='multi.pdf',
        ).select_related('data')
        req = SSRMRequest(start_row=0, end_row=100)
        result = process_ssrm_request(self.config, req, qs)
        self.assertEqual(result['rowCount'], 3)


class ExpanderPageSpanningDocsTest(_ExpanderBase):
    def test_page_spanning_two_documents(self):
        # Total: empty(1) + multi(3) + single(1) = 5 rows, sorted by name
        # name asc: empty.pdf(1), multi.pdf(3), single.pdf(1)
        # Page startRow=0, endRow=2 => first 2 rows: empty(1 row) + multi(1st item)
        result = self._process({'startRow': 0, 'endRow': 2})
        self.assertEqual(len(result['rowData']), 2)
        self.assertEqual(result['rowCount'], 5)


class ExpanderLastPagePartialTest(_ExpanderBase):
    def test_last_page_partial(self):
        result = self._process({'startRow': 4, 'endRow': 100})
        self.assertEqual(len(result['rowData']), 1)
        self.assertEqual(result['rowCount'], 5)


class ExpanderWithFilterTest(_ExpanderBase):
    def test_filter_narrows_to_one_doc(self):
        result = self._process({
            'startRow': 0, 'endRow': 100,
            'filterModel': {
                'status': {'filterType': 'set', 'values': ['PENDING']},
            },
        })
        # Only empty.pdf is PENDING, expands to 1 row
        self.assertEqual(result['rowCount'], 1)


class ExpanderWithSortTest(_ExpanderBase):
    def test_sort_changes_document_order(self):
        result_asc = self._process({
            'startRow': 0, 'endRow': 100,
            'sortModel': [{'colId': 'name', 'sort': 'asc'}],
        })
        result_desc = self._process({
            'startRow': 0, 'endRow': 100,
            'sortModel': [{'colId': 'name', 'sort': 'desc'}],
        })
        first_asc = result_asc['rowData'][0]['name']
        first_desc = result_desc['rowData'][0]['name']
        self.assertNotEqual(first_asc, first_desc)


# ===========================================================================
# SSRMRequest
# ===========================================================================

class SSRMRequestFromBodyMinimalTest(TestCase):
    def test_minimal_body(self):
        req = SSRMRequest.from_body({'startRow': 5, 'endRow': 25})
        self.assertEqual(req.start_row, 5)
        self.assertEqual(req.end_row, 25)


class SSRMRequestFromBodyEmptyTest(TestCase):
    def test_empty_body_defaults(self):
        req = SSRMRequest.from_body({})
        self.assertEqual(req.start_row, 0)
        self.assertEqual(req.end_row, 100)
        self.assertEqual(req.row_group_cols, [])
        self.assertEqual(req.group_keys, [])
        self.assertEqual(req.filter_model, {})
        self.assertEqual(req.sort_model, [])


class SSRMRequestIsGroupingTrueTest(TestCase):
    def test_is_grouping_true(self):
        req = SSRMRequest(row_group_cols=[{'field': 'status'}])
        self.assertTrue(req.is_grouping)


class SSRMRequestIsGroupingFalseTest(TestCase):
    def test_is_grouping_false(self):
        req = SSRMRequest()
        self.assertFalse(req.is_grouping)


class SSRMRequestIsLeafLevel0Test(TestCase):
    def test_is_leaf_at_level_0_with_group_cols(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'status'}],
            group_keys=[],
        )
        self.assertFalse(req.is_leaf_level)


class SSRMRequestIsLeafLevel1Test(TestCase):
    def test_is_leaf_at_level_1_single_group(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'status'}],
            group_keys=['COMPLETED'],
        )
        self.assertTrue(req.is_leaf_level)


class SSRMRequestIsLeafLevel2Test(TestCase):
    def test_is_leaf_at_level_2_multi_group(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'status'}, {'field': 'state'}],
            group_keys=['COMPLETED', 'TX'],
        )
        self.assertTrue(req.is_leaf_level)


class SSRMRequestGroupLevelTest(TestCase):
    def test_group_level_at_different_depths(self):
        req0 = SSRMRequest(group_keys=[])
        req1 = SSRMRequest(group_keys=['A'])
        req2 = SSRMRequest(group_keys=['A', 'B'])
        self.assertEqual(req0.group_level, 0)
        self.assertEqual(req1.group_level, 1)
        self.assertEqual(req2.group_level, 2)


class SSRMRequestPageSizeTest(TestCase):
    def test_page_size_calculation(self):
        req = SSRMRequest(start_row=10, end_row=60)
        self.assertEqual(req.page_size, 50)


class SSRMRequestExtraKeysTest(TestCase):
    def test_extra_keys_preserved(self):
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 100,
            'search': 'hello',
            'explode': True,
            'customFlag': 42,
        })
        self.assertEqual(req.extra['search'], 'hello')
        self.assertTrue(req.extra['explode'])
        self.assertEqual(req.extra['customFlag'], 42)


# ===========================================================================
# SSRMConfig
# ===========================================================================

class SSRMConfigGetFieldsDictTest(TestCase):
    def test_get_fields_dict_correct_mapping(self):
        fields = [
            FieldDef('name', 'name'),
            FieldDef('status', 'status'),
        ]
        config = SSRMConfig(fields=fields)
        d = config.get_fields_dict()
        self.assertIn('name', d)
        self.assertIn('status', d)
        self.assertEqual(d['name'].orm_path, 'name')


class SSRMConfigGetFieldsDictEmptyTest(TestCase):
    def test_get_fields_dict_with_no_fields(self):
        config = SSRMConfig(fields=[])
        self.assertEqual(config.get_fields_dict(), {})


class SSRMConfigMaxPageSizeDefaultTest(TestCase):
    def test_max_page_size_default_is_500(self):
        config = SSRMConfig(fields=[])
        self.assertEqual(config.max_page_size, 500)


class SSRMConfigDefaultSortTest(TestCase):
    def test_default_sort_is_neg_pk(self):
        config = SSRMConfig(fields=[])
        self.assertEqual(config.default_sort, ['-pk'])
