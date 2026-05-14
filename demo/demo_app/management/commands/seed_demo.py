"""Seed the demo DB with ~5000 Sale rows so the grid has data to chew on."""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from demo_app.models import Sale


REGIONS = ['North', 'South', 'East', 'West', 'Central']
CATEGORIES = ['Electronics', 'Clothing', 'Books', 'Home', 'Toys', 'Sports']
PRODUCTS = {
    'Electronics': ['Headphones', 'Smartwatch', 'Tablet', 'Camera', 'Speaker'],
    'Clothing':    ['T-Shirt', 'Jeans', 'Jacket', 'Sneakers', 'Hat'],
    'Books':       ['Novel', 'Cookbook', 'Atlas', 'Biography', 'Textbook'],
    'Home':        ['Lamp', 'Pillow', 'Mug', 'Vase', 'Rug'],
    'Toys':        ['Puzzle', 'Action Figure', 'Board Game', 'Plush', 'Lego Set'],
    'Sports':      ['Tennis Racket', 'Football', 'Yoga Mat', 'Dumbbell', 'Helmet'],
}
SALES_REPS = ['Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank', 'Grace', 'Heidi']


class Command(BaseCommand):
    help = 'Populate the demo DB with sample Sale rows.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=5000)
        parser.add_argument('--clear', action='store_true',
                            help='Delete existing Sales before seeding.')

    def handle(self, *args, **opts):
        count = opts['count']
        if opts['clear']:
            n = Sale.objects.count()
            Sale.objects.all().delete()
            self.stdout.write(f'  Cleared {n} existing rows.')

        now = timezone.now()
        rng = random.Random(42)
        rows = []
        for _ in range(count):
            cat = rng.choice(CATEGORIES)
            rows.append(Sale(
                region=rng.choice(REGIONS),
                product=rng.choice(PRODUCTS[cat]),
                category=cat,
                quantity=rng.randint(1, 50),
                unit_price=Decimal(f'{rng.uniform(5, 500):.2f}'),
                sold_at=now - timedelta(
                    days=rng.randint(0, 730),
                    hours=rng.randint(0, 23),
                    minutes=rng.randint(0, 59),
                ),
                sales_rep=rng.choice(SALES_REPS),
                metadata={'channel': rng.choice(['online', 'retail', 'wholesale'])},
            ))
        Sale.objects.bulk_create(rows, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f'  Created {count} Sale rows.'))
