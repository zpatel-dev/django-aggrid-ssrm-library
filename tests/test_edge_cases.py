"""
Edge-case tests that expose real bugs in the SSRM module.

Each test is named after the bug it proves.  They should FAIL before the
fix is applied and PASS afterwards.
"""
from django.test import TestCase

from tests.test_app.models import Item, ItemData
from aggrid_ssrm import (
    FieldDef, SSRMConfig, SSRMRequest,
    default_row_builder, process_ssrm_request,
)
from aggrid_ssrm.filters import apply_filters
from aggrid_ssrm.grouping import handle_grouped_request


def _row_builder(instance, field_defs):
    row = {}
    for fd in field_defs:
        if fd.value_getter:
            row[fd.col_id] = fd.value_getter(instance)
        else:
            row[fd.col_id] = getattr(instance, fd.col_id, None)
    return row


class Bug1_JSONGroupKeyTypeMismatch(TestCase):
    """
    _aggregate_python stringifies all values.  When the JSON stores an
    integer and the user expands the group, the string key '3' doesn't
    match integer 3 in the DB → the expanded group returns 0 rows.
    """

    def setUp(self):
        for i in range(4):
            doc = Item.objects.create(
                name=f'd{i}.pdf',
                status='COMPLETED', source=f'/tmp/d{i}.pdf',
            )
            # amount is stored as integer in JSON
            ItemData.objects.create(
                item=doc,
                payload={'amount': 100 if i < 3 else 200},
            )

        self.field_defs = [
            FieldDef('name', 'name'),
            FieldDef('amount', 'data__payload__amount',
                     is_json=True, field_type='number',
                     value_getter=lambda d: (
                         d.data.payload.get('amount')
                         if hasattr(d, 'data') else None)),
        ]
        self.fields_dict = {fd.col_id: fd for fd in self.field_defs}

    def test_drill_down_into_json_integer_group(self):
        """Expand a group whose key came from a stringified integer."""
        # First: get group rows (top level)
        req_top = SSRMRequest(
            row_group_cols=[{'field': 'amount', 'colId': 'amount'}],
            group_keys=[],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        top = handle_grouped_request(
            qs, req_top, self.fields_dict,
            _row_builder, self.field_defs, ['-pk'],
        )
        # Should have 2 groups: 100 (3 docs) and 200 (1 doc)
        self.assertEqual(top['rowCount'], 2)

        # Now drill down using the key AG Grid would send back (string)
        group_key = str(top['rowData'][0]['amount'])   # e.g. '100'
        req_drill = SSRMRequest(
            row_group_cols=[{'field': 'amount', 'colId': 'amount'}],
            group_keys=[group_key],
            start_row=0, end_row=100,
        )
        leaf = handle_grouped_request(
            qs, req_drill, self.fields_dict,
            _row_builder, self.field_defs, ['-pk'],
        )
        # BUG: without fix this returns 0 because '100' != 100
        self.assertGreater(leaf['rowCount'], 0,
                           "Drill-down into JSON integer group returned 0 rows")


class Bug2_CombinedFilterDropsSetCondition(TestCase):
    """
    _Q_HANDLERS doesn't include 'set', so a combined filter with a set
    condition inside silently drops it — only the other condition applies.
    """

    def setUp(self):
        for name, status in [
            ('a.pdf', 'COMPLETED'), ('b.pdf', 'PENDING'),
            ('c.pdf', 'FAILED'), ('d.pdf', 'COMPLETED'),
        ]:
            Item.objects.create(
                name=name,
                status=status, source=f'/tmp/{name}',
            )
        self.fields = {
            'status': FieldDef('status', 'status', field_type='set'),
        }

    def test_combined_or_with_set_condition(self):
        """OR(set:{COMPLETED}, set:{FAILED}) should match 3 docs."""
        qs = Item.objects.all()
        fm = {'status': {
            'operator': 'OR',
            'condition1': {'filterType': 'set', 'values': ['COMPLETED']},
            'condition2': {'filterType': 'set', 'values': ['FAILED']},
        }}
        result = apply_filters(qs, fm, self.fields)
        # BUG: without fix, both conditions are dropped → returns all 4
        self.assertEqual(result.count(), 3)


class Bug3_GroupableNotEnforced(TestCase):
    """
    A field with groupable=False can still be grouped on because
    handle_grouped_request never checks the flag.
    """

    def setUp(self):
        for i in range(3):
            Item.objects.create(
                name=f'd{i}.pdf',
                status='COMPLETED', source=f'/tmp/d{i}.pdf',
            )

        self.field_defs = [
            FieldDef('id', 'id', groupable=False),
            FieldDef('name', 'name'),
        ]
        self.fields_dict = {fd.col_id: fd for fd in self.field_defs}

    def test_groupable_false_returns_empty(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'id', 'colId': 'id'}],
            group_keys=[],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all()
        result = handle_grouped_request(
            qs, req, self.fields_dict,
            _row_builder, self.field_defs, ['-pk'],
        )
        # BUG: without fix, this returns group rows for id
        self.assertEqual(result['rowData'], [])
        self.assertEqual(result['rowCount'], 0)


class Bug4_MaxPageSizeNotEnforcedInGrouping(TestCase):
    """
    max_page_size is enforced in _handle_flat but NOT in any of the
    grouping paths (group-level or leaf-level).
    """

    def setUp(self):
        for i in range(10):
            Item.objects.create(
                name=f'd{i}.pdf',
                status='COMPLETED' if i < 5 else 'PENDING',
                source=f'/tmp/d{i}.pdf',
            )

        self.config = SSRMConfig(
            fields=[
                FieldDef('name', 'name'),
                FieldDef('status', 'status', field_type='set'),
            ],
            default_sort=['-pk'],
            max_page_size=2,
        )

    def test_leaf_level_respects_max_page_size(self):
        """Drill down with endRow=9999 should still be capped."""
        req = SSRMRequest.from_body({
            'startRow': 0, 'endRow': 9999,
            'rowGroupCols': [{'field': 'status', 'colId': 'status'}],
            'groupKeys': ['COMPLETED'],
        })
        qs = Item.objects.all()
        result = process_ssrm_request(self.config, req, qs)
        # BUG: without fix, returns all 5 COMPLETED rows
        self.assertLessEqual(len(result['rowData']), 2)


class Bug5_ValueAliasCollidesWithChildCount(TestCase):
    """
    If a value column's col_id is 'childCount', the annotation
    overwrites the group count.
    """

    def setUp(self):
        for i in range(5):
            doc = Item.objects.create(
                name=f'd{i}.pdf',
                status='COMPLETED' if i < 3 else 'PENDING',
                source=f'/tmp/d{i}.pdf',
            )
            ItemData.objects.create(
                item=doc, payload={},
                review_count=i,
            )

        self.field_defs = [
            FieldDef('status', 'status', field_type='set'),
            # Deliberately named to collide
            FieldDef('childCount', 'data__review_count',
                     field_type='number'),
        ]
        self.fields_dict = {fd.col_id: fd for fd in self.field_defs}

    def test_value_col_named_childcount_doesnt_corrupt_groups(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'status', 'colId': 'status'}],
            group_keys=[],
            value_cols=[{'field': 'childCount', 'aggFunc': 'sum'}],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict,
            _row_builder, self.field_defs, ['-pk'],
        )
        # childCount should be the COUNT of docs, not the SUM
        for row in result['rowData']:
            if row['status'] == 'COMPLETED':
                self.assertEqual(row['childCount'], 3,
                                 "childCount was overwritten by value aggregation")


class Bug6_AggregratePythonMergesNoneAndEmpty(TestCase):
    """
    _aggregate_python maps both None and '' to '' — they merge
    into one group with inflated count.
    """

    def setUp(self):
        # 2 docs with state='TX', 1 with state=None, 1 with state=''
        for i, state in enumerate(['TX', 'TX', None, '']):
            doc = Item.objects.create(
                name=f'd{i}.pdf',
                status='COMPLETED', source=f'/tmp/d{i}.pdf',
            )
            ed = {'state': state} if state is not None else {}
            ItemData.objects.create(item=doc, payload=ed)

        self.field_defs = [
            FieldDef('state', 'data__payload__state', is_json=True),
        ]
        self.fields_dict = {fd.col_id: fd for fd in self.field_defs}

    def test_none_values_excluded_from_groups(self):
        """None/missing values should not appear as a group."""
        req = SSRMRequest(
            row_group_cols=[{'field': 'state', 'colId': 'state'}],
            group_keys=[],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict,
            _row_builder, self.field_defs, ['-pk'],
        )
        group_values = [r['state'] for r in result['rowData']]
        # BUG: without fix, None and '' merge into one '' group with count=2
        # After fix: None rows excluded, '' rows kept, TX=2
        self.assertNotIn(None, group_values,
                         "None should not appear as a group value")
        tx_row = [r for r in result['rowData'] if r['state'] == 'TX']
        self.assertEqual(tx_row[0]['childCount'], 2)


class Bug7_DefaultRowBuilderMissingRelation(TestCase):
    """
    Regression test: default_row_builder with _resolve_orm_path must
    safely handle Documents that have no related ItemData.
    """

    def setUp(self):
        # Doc WITHOUT ItemData (e.g., PENDING status)
        self.doc_no_data = Item.objects.create(
            name='orphan.pdf',
            status='PENDING', source='/tmp/orphan.pdf',
        )
        # Doc WITH ItemData
        doc_with = Item.objects.create(
            name='complete.pdf',
            status='COMPLETED', source='/tmp/complete.pdf',
        )
        ItemData.objects.create(
            item=doc_with,
            payload={'county': 'Harris'},
            review_count=2,
        )

        self.field_defs = [
            FieldDef('name', 'name'),
            FieldDef('review_count', 'data__review_count'),
            FieldDef('county', 'data__payload__county', is_json=True),
        ]

    def test_default_builder_no_crash_on_missing_data(self):
        """default_row_builder should return None for missing relation fields."""
        doc = Item.objects.select_related('data').get(pk=self.doc_no_data.pk)
        row = default_row_builder(doc, self.field_defs)
        self.assertEqual(row['name'], 'orphan.pdf')
        self.assertIsNone(row['review_count'])
        self.assertIsNone(row['county'])

    def test_default_builder_works_with_data(self):
        doc = Item.objects.select_related('data').get(name='complete.pdf')
        row = default_row_builder(doc, self.field_defs)
        self.assertEqual(row['name'], 'complete.pdf')
        self.assertEqual(row['review_count'], 2)
        self.assertEqual(row['county'], 'Harris')


class Bug8_ArrayNestedJSONFieldsInvisible(TestCase):
    """
    When payload uses {"items": [{col: val}, ...]} structure,
    the ORM path data__payload__col returns None because the
    value is inside the array, not at the top level.

    column_values and grouping must use value_getter to reach into
    the array and extract/flatten values.
    """

    def setUp(self):
        # Doc 1: 2 tracts in ALPHA county
        doc1 = Item.objects.create(
            name='order1.pdf',
            status='COMPLETED', source='/tmp/order1.pdf',
        )
        ItemData.objects.create(
            item=doc1,
            payload={'items': [
                {'COUNTY': 'ALPHA', 'STATE': 'OK'},
                {'COUNTY': 'ALPHA', 'STATE': 'OK'},
            ]},
        )
        # Doc 2: 1 tract in BETA county
        doc2 = Item.objects.create(
            name='order2.pdf',
            status='COMPLETED', source='/tmp/order2.pdf',
        )
        ItemData.objects.create(
            item=doc2,
            payload={'items': [
                {'COUNTY': 'BETA', 'STATE': 'OK'},
            ]},
        )

        def _vg(col):
            def getter(d):
                extracted = d.data.payload if hasattr(d, 'data') else {}
                items = extracted.get('items', []) if isinstance(extracted, dict) else []
                if isinstance(extracted, dict) and col in extracted:
                    return extracted.get(col)
                if isinstance(items, list) and items:
                    return [it.get(col) for it in items if isinstance(it, dict) and col in it]
                return None
            return getter

        json_cfg = {
            'table': 'test_app_itemdata',
            'json_column': 'payload',
            'array_path': '$.items',
            'fk_column': 'item_id',
        }

        self.field_defs = [
            FieldDef('name', 'name'),
            FieldDef('COUNTY', 'data__payload__COUNTY',
                     is_json=True, value_getter=_vg('COUNTY'),
                     json_array_config=json_cfg),
            FieldDef('STATE', 'data__payload__STATE',
                     is_json=True, value_getter=_vg('STATE'),
                     json_array_config=json_cfg),
        ]
        self.fields_dict = {fd.col_id: fd for fd in self.field_defs}

    def test_distinct_values_finds_array_nested_values(self):
        """Set Filter dropdown should show ALPHA and BETA."""
        from aggrid_ssrm.column_values import get_distinct_values
        qs = Item.objects.all().select_related('data')
        values = get_distinct_values(qs, 'COUNTY', self.fields_dict)
        self.assertEqual(sorted(values), ['ALPHA', 'BETA'])

    def test_grouping_sees_array_nested_values(self):
        """Grouping by COUNTY should show 2 groups, not 1 empty group."""
        req = SSRMRequest(
            row_group_cols=[{'field': 'COUNTY', 'colId': 'COUNTY'}],
            group_keys=[],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict,
            _row_builder, self.field_defs, ['-pk'],
        )
        self.assertEqual(result['rowCount'], 2)
        counties = {r['COUNTY'] for r in result['rowData']}
        self.assertEqual(counties, {'ALPHA', 'BETA'})

    def test_grouping_counts_items_not_documents(self):
        """ALPHA has 2 items (across 1 doc), BETA has 1 item."""
        req = SSRMRequest(
            row_group_cols=[{'field': 'COUNTY', 'colId': 'COUNTY'}],
            group_keys=[],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict,
            _row_builder, self.field_defs, ['-pk'],
        )
        counts = {r['COUNTY']: r['childCount'] for r in result['rowData']}
        self.assertEqual(counts['ALPHA'], 2)
        self.assertEqual(counts['BETA'], 1)
