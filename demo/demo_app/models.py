from django.db import models


class AthleteEvent(models.Model):
    """
    One athlete's participation in one Olympic event.

    Data source: TidyTuesday 2024-08-06 ``olympics.csv`` (~271,000 rows,
    Athens 1896 – Rio 2016), originally compiled from the Kaggle dataset
    "120 years of Olympic history: athletes and results" by heesoo37.
    Shipped gzipped in ``demo/data/olympics.csv.gz`` and loaded by the
    ``seed_demo`` management command.
    """
    athlete_id = models.IntegerField(db_index=True)        # original 'id'; not unique
    name       = models.CharField(max_length=200)
    sex        = models.CharField(max_length=1)            # 'M' or 'F'
    age        = models.IntegerField(null=True, blank=True)
    height     = models.IntegerField(null=True, blank=True)   # cm
    weight     = models.IntegerField(null=True, blank=True)   # kg
    team       = models.CharField(max_length=120)
    noc        = models.CharField(max_length=3)            # IOC country code
    games      = models.CharField(max_length=40)           # e.g. '1992 Summer'
    year       = models.IntegerField()
    season     = models.CharField(max_length=10)           # 'Summer' or 'Winter'
    city       = models.CharField(max_length=80)
    sport      = models.CharField(max_length=80)
    event      = models.CharField(max_length=200)
    medal      = models.CharField(max_length=10, null=True, blank=True)  # Gold/Silver/Bronze/None

    class Meta:
        indexes = [
            models.Index(fields=['noc']),
            models.Index(fields=['sport']),
            models.Index(fields=['year']),
            models.Index(fields=['season']),
            models.Index(fields=['medal']),
        ]

    def __str__(self):
        return f'{self.name} — {self.event} ({self.games})'
