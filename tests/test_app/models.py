"""
Minimal models used by the test suite.

A main model (``Item``) plus a 1:1 related model with a ``JSONField``
(``ItemData``) — the same shape the SSRM engine is most often used
against. Field names are intentionally generic.
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
