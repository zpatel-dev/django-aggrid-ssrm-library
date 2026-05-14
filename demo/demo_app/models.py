from django.db import models


class Sale(models.Model):
    """Single sales-record row that AG Grid SSRM serves up."""
    region = models.CharField(max_length=50)
    product = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    sold_at = models.DateTimeField()
    sales_rep = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['region']),
            models.Index(fields=['category']),
            models.Index(fields=['sold_at']),
        ]

    def __str__(self):
        return f'{self.product} x{self.quantity} ({self.region})'
