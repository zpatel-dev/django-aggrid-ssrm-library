from django.test import TestCase

from tests.test_app.models import Item, ItemData
from aggrid_ssrm.fields import FieldDef
from aggrid_ssrm.grouping import handle_grouped_request
from aggrid_ssrm.request import SSRMRequest


def _row_builder(instance, field_defs):
    row = {}
    for fd in field_defs:
        if fd.value_getter:
            row[fd.col_id] = fd.value_getter(instance)
        else:
            row[fd.col_id] = getattr(instance, fd.col_id, None)
    return row


class GroupingTest(TestCase):
    def setUp(self):
        statuses = ['COMPLETED', 'COMPLETED', 'PENDING', 'FAILED', 'PENDING']
        for i, status in enumerate(statuses):
            doc = Item.objects.create(
                name=f'doc{i}.pdf',
                status=status, source=f'/tmp/doc{i}.pdf',
            )
            ItemData.objects.create(
                item=doc,
                payload={'state': 'TX' if i < 3 else 'CA'},
                review_count=i,
            )

        self.field_defs = [
            FieldDef('name', 'name'),
            FieldDef('status', 'status', field_type='set'),
            FieldDef('state', 'data__payload__state', is_json=True,
                     value_getter=lambda d: d.data.payload.get('state') if hasattr(d, 'data') else None),
        ]
        self.fields_dict = {fd.col_id: fd for fd in self.field_defs}

    def test_group_by_direct_field(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'status', 'colId': 'status'}],
            group_keys=[],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict, _row_builder, self.field_defs, ['-pk'],
        )
        self.assertIn('rowData', result)
        self.assertIn('rowCount', result)
        # 3 distinct statuses: COMPLETED, FAILED, PENDING
        self.assertEqual(result['rowCount'], 3)
        statuses = {r['status'] for r in result['rowData']}
        self.assertEqual(statuses, {'COMPLETED', 'FAILED', 'PENDING'})
        for r in result['rowData']:
            self.assertIn('childCount', r)

    def test_group_child_counts_correct(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'status', 'colId': 'status'}],
            group_keys=[],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict, _row_builder, self.field_defs, ['-pk'],
        )
        counts = {r['status']: r['childCount'] for r in result['rowData']}
        self.assertEqual(counts['COMPLETED'], 2)
        self.assertEqual(counts['PENDING'], 2)
        self.assertEqual(counts['FAILED'], 1)

    def test_drill_down_to_leaf(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'status', 'colId': 'status'}],
            group_keys=['COMPLETED'],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict, _row_builder, self.field_defs, ['-pk'],
        )
        self.assertEqual(result['rowCount'], 2)
        for r in result['rowData']:
            self.assertIn('name', r)

    def test_group_by_json_field(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'state', 'colId': 'state'}],
            group_keys=[],
            start_row=0, end_row=100,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict, _row_builder, self.field_defs, ['-pk'],
        )
        self.assertEqual(result['rowCount'], 2)
        states = {r['state'] for r in result['rowData']}
        self.assertEqual(states, {'CA', 'TX'})

    def test_group_pagination(self):
        req = SSRMRequest(
            row_group_cols=[{'field': 'status', 'colId': 'status'}],
            group_keys=[],
            start_row=0, end_row=2,
        )
        qs = Item.objects.all().select_related('data')
        result = handle_grouped_request(
            qs, req, self.fields_dict, _row_builder, self.field_defs, ['-pk'],
        )
        self.assertEqual(result['rowCount'], 3)  # total groups
        self.assertEqual(len(result['rowData']), 2)  # page of 2
