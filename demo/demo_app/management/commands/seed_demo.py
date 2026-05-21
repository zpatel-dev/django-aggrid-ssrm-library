"""
Load TidyTuesday's '120 Years of Olympic History' dataset into the demo DB.

The gzipped CSV (~5 MB compressed, ~34 MB raw, 271,116 rows) ships in
``demo/data/olympics.csv.gz``.  Original source:
https://github.com/rfordatascience/tidytuesday/tree/main/data/2024/2024-08-06
"""
import csv
import gzip
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from demo_app.models import AthleteEvent


DATA_FILE = Path(__file__).resolve().parents[3] / 'data' / 'olympics.csv.gz'


def _int_or_none(value):
    if value is None or value == '' or value == 'NA':
        return None
    try:
        return int(float(value))   # height/weight sometimes have decimals
    except (ValueError, TypeError):
        return None


def _medal_or_none(value):
    if not value or value == 'NA':
        return None
    return value


class Command(BaseCommand):
    help = 'Load the 120-Years-of-Olympic-History dataset (~271k rows) into the demo DB.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true',
                            help='Delete existing rows before loading.')
        parser.add_argument('--limit', type=int, default=0,
                            help='Load only the first N rows (0 = all).')
        parser.add_argument('--batch-size', type=int, default=5000,
                            help='Bulk insert batch size (default 5000).')

    def handle(self, *args, **opts):
        if not DATA_FILE.exists():
            raise CommandError(
                f'Dataset not found at {DATA_FILE}.  '
                f'It ships with the repo at demo/data/olympics.csv.gz.'
            )

        if opts['clear']:
            n = AthleteEvent.objects.count()
            AthleteEvent.objects.all().delete()
            self.stdout.write(f'  Cleared {n} existing rows.')

        limit = opts['limit']
        batch_size = opts['batch_size']
        batch: list[AthleteEvent] = []
        total = 0

        with gzip.open(DATA_FILE, mode='rt', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                batch.append(AthleteEvent(
                    athlete_id=_int_or_none(row.get('id')) or 0,
                    name=row.get('name', '')[:200],
                    sex=row.get('sex', '')[:1],
                    age=_int_or_none(row.get('age')),
                    height=_int_or_none(row.get('height')),
                    weight=_int_or_none(row.get('weight')),
                    team=row.get('team', '')[:120],
                    noc=row.get('noc', '')[:3],
                    games=row.get('games', '')[:40],
                    year=_int_or_none(row.get('year')) or 0,
                    season=row.get('season', '')[:10],
                    city=row.get('city', '')[:80],
                    sport=row.get('sport', '')[:80],
                    event=row.get('event', '')[:200],
                    medal=_medal_or_none(row.get('medal')),
                ))
                if len(batch) >= batch_size:
                    AthleteEvent.objects.bulk_create(batch, batch_size=batch_size)
                    total += len(batch)
                    batch.clear()
                    self.stdout.write(f'  Loaded {total:,} rows…', ending='\r')
                    self.stdout.flush()
                if limit and total + len(batch) >= limit:
                    break

        if batch:
            if limit:
                batch = batch[: max(0, limit - total)]
            AthleteEvent.objects.bulk_create(batch, batch_size=batch_size)
            total += len(batch)

        self.stdout.write(self.style.SUCCESS(
            f'\n  Loaded {total:,} Olympic athlete-event records.'
        ))
