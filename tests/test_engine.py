from django.test import TestCase

from tests.test_app.models import Item, ItemData
from aggrid_ssrm import FieldDef, SSRMConfig, SSRMRequest, process_ssrm_request


class EngineIntegrationTest(TestCase):
    def setUp(self):
        for i in range(10):
            doc = Item.objects.create(
                name=f'file{i}.pdf',
                status='COMPLETED' if i % 2 == 0 else 'PENDING',
                source=f'/tmp/file{i}.pdf',
            )
            ItemData.objects.create(
                item=doc,
                payload={'county': f'County_{i % 3}', 'amount': i * 100},
                review_count=i % 2,
            )

        def _vg(col):
            def getter(d):
                ed = d.data.payload if hasattr(d, 'data') else {}
                return ed.get(col) if isinstance(ed, dict) else None
            return getter

        self.config = SSRMConfig(
            fields=[
                FieldDef('id', 'id', sortable=False, filterable=False, groupable=False,
                         value_getter=lambda d: d.id),
                FieldDef('name', 'name'),
                FieldDef('status', 'status', field_type='set'),
                FieldDef('review_count', 'data__review_count', field_type='number',
                         value_getter=lambda d: d.data.review_count if hasattr(d, 'data') else 0),
                FieldDef('county', 'data__payload__county', is_json=True,
                         value_getter=_vg('county')),
                FieldDef('amount', 'data__payload__amount', is_json=True, field_type='number',
                         value_getter=_vg('amount')),
            ],
            default_sort=['-pk'],
            search_fields=['name', 'status'],
        )

    def _qs(self):
        return Item.objects.all().select_related('data')

    # ── Flat requests ───────────────────────────────────────────────────

    def test_flat_pagination(self):
        req = SSRMRequest(start_row=0, end_row=3)
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(len(result['rowData']), 3)
        self.assertEqual(result['rowCount'], 10)

    def test_flat_second_page(self):
        req = SSRMRequest(start_row=8, end_row=20)
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(len(result['rowData']), 2)  # only 2 left
        self.assertEqual(result['rowCount'], 10)

    def test_flat_with_search(self):
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 100,
            'search': 'file0',
        })
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(result['rowCount'], 1)

    def test_flat_with_set_filter(self):
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 100,
            'filterModel': {'status': {'filterType': 'set', 'values': ['COMPLETED']}},
        })
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(result['rowCount'], 5)

    def test_flat_with_sort(self):
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 3,
            'sortModel': [{'colId': 'name', 'sort': 'desc'}],
        })
        result = process_ssrm_request(self.config, req, self._qs())
        filenames = [r['name'] for r in result['rowData']]
        self.assertEqual(filenames, sorted(filenames, reverse=True))

    def test_max_page_size_enforced(self):
        config = SSRMConfig(
            fields=self.config.fields,
            default_sort=['-pk'],
            max_page_size=2,
        )
        req = SSRMRequest(start_row=0, end_row=100)
        result = process_ssrm_request(config, req, self._qs())
        self.assertLessEqual(len(result['rowData']), 2)

    # ── Grouped requests ────────────────────────────────────────────────

    def test_grouped_by_status(self):
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 100,
            'rowGroupCols': [{'field': 'status', 'colId': 'status'}],
            'groupKeys': [],
        })
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(result['rowCount'], 2)  # COMPLETED, PENDING
        for r in result['rowData']:
            self.assertIn('childCount', r)

    def test_grouped_drill_down(self):
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 100,
            'rowGroupCols': [{'field': 'status', 'colId': 'status'}],
            'groupKeys': ['COMPLETED'],
        })
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(result['rowCount'], 5)
        for r in result['rowData']:
            self.assertIn('name', r)

    def test_grouped_with_filter(self):
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 100,
            'rowGroupCols': [{'field': 'status', 'colId': 'status'}],
            'groupKeys': [],
            'filterModel': {'status': {'filterType': 'set', 'values': ['COMPLETED']}},
        })
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(result['rowCount'], 1)
        self.assertEqual(result['rowData'][0]['status'], 'COMPLETED')

    def test_grouped_by_json_field(self):
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 100,
            'rowGroupCols': [{'field': 'county', 'colId': 'county'}],
            'groupKeys': [],
        })
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(result['rowCount'], 3)  # County_0, County_1, County_2
        total_children = sum(r['childCount'] for r in result['rowData'])
        self.assertEqual(total_children, 10)

    # ── Row data shape ──────────────────────────────────────────────────

    def test_row_contains_all_fields(self):
        req = SSRMRequest(start_row=0, end_row=1)
        result = process_ssrm_request(self.config, req, self._qs())
        row = result['rowData'][0]
        for fd in self.config.fields:
            self.assertIn(fd.col_id, row, f'Missing field: {fd.col_id}')


class RowExpanderTest(TestCase):
    """Test the row_expander virtual pagination path."""

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
        # Doc with no items
        doc3 = Item.objects.create(
            name='empty.pdf',
            status='PENDING', source='/tmp/empty.pdf',
        )
        ItemData.objects.create(
            item=doc3, payload={'note': 'no items'},
        )

        def _expander(instance, field_defs):
            """Expand items[] into multiple rows."""
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

        def _vg(col):
            def getter(d):
                ed = d.data.payload if hasattr(d, 'data') else {}
                return ed.get(col) if isinstance(ed, dict) else None
            return getter

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
        )

    def _qs(self):
        return Item.objects.all().select_related('data')

    def test_total_row_count_is_expanded(self):
        """3 items + 1 item + 1 (no items) = 5 virtual rows."""
        req = SSRMRequest(start_row=0, end_row=100)
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(result['rowCount'], 5)

    def test_expanded_rows_have_item_values(self):
        req = SSRMRequest(start_row=0, end_row=100)
        result = process_ssrm_request(self.config, req, self._qs())
        tracts = [r['tract'] for r in result['rowData'] if r['tract']]
        self.assertEqual(sorted(tracts), ['T1', 'T2', 'T3', 'T4'])

    def test_virtual_pagination_page_1(self):
        req = SSRMRequest(start_row=0, end_row=2)
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(len(result['rowData']), 2)
        self.assertEqual(result['rowCount'], 5)  # total still 5

    def test_virtual_pagination_page_2(self):
        req = SSRMRequest(start_row=2, end_row=4)
        result = process_ssrm_request(self.config, req, self._qs())
        self.assertEqual(len(result['rowData']), 2)

    def test_search_with_expander(self):
        config = SSRMConfig(
            fields=self.config.fields,
            row_expander=self.config.row_expander,
            default_sort=['name'],
            search_fields=['name'],
        )
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 100, 'search': 'multi',
        })
        result = process_ssrm_request(config, req, self._qs())
        # Only multi.pdf matched → 3 expanded rows
        self.assertEqual(result['rowCount'], 3)

    def test_max_page_size_enforced_with_expander(self):
        config = SSRMConfig(
            fields=self.config.fields,
            row_expander=self.config.row_expander,
            default_sort=['name'],
            max_page_size=2,
        )
        req = SSRMRequest(start_row=0, end_row=9999)
        result = process_ssrm_request(config, req, self._qs())
        self.assertLessEqual(len(result['rowData']), 2)
        self.assertEqual(result['rowCount'], 5)


class SSRMRequestTest(TestCase):
    def test_from_body_parses_known_keys(self):
        body = {
            'startRow': 10, 'endRow': 50,
            'rowGroupCols': [{'field': 'x'}],
            'groupKeys': ['a'],
            'filterModel': {'f': {}},
            'sortModel': [{'colId': 'x', 'sort': 'asc'}],
            'pivotMode': True,
            'search': 'hello',
            'explode': True,
        }
        req = SSRMRequest.from_body(body)
        self.assertEqual(req.start_row, 10)
        self.assertEqual(req.end_row, 50)
        self.assertEqual(req.group_keys, ['a'])
        self.assertTrue(req.pivot_mode)
        self.assertEqual(req.extra['search'], 'hello')
        self.assertTrue(req.extra['explode'])

    def test_is_grouping(self):
        req = SSRMRequest(row_group_cols=[{'field': 'x'}])
        self.assertTrue(req.is_grouping)

    def test_not_grouping(self):
        req = SSRMRequest()
        self.assertFalse(req.is_grouping)

    def test_page_size(self):
        req = SSRMRequest(start_row=10, end_row=60)
        self.assertEqual(req.page_size, 50)
