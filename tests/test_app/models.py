"""
Minimal models used by the test suite.

These mirror the shape of the source project's Document / DocumentData
pair (a main model + a 1:1 related model with a JSONField), with generic
names so the tests document general-purpose use of the library.
"""
from django.db import models


class Item(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50, default='PENDING')
    source = models.CharField(max_length=500)
    modified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    data: "ItemData"  # type hint for the related ItemData

    def __str__(self):
        return f'{self.name} ({self.status})'


class ItemData(models.Model):
    item = models.OneToOneField(
        Item, on_delete=models.CASCADE, related_name='data',
    )
    payload = models.JSONField(default=dict)
    review_count = models.IntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Data for {self.item.name}'
