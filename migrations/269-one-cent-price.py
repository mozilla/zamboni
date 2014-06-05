from decimal import Decimal
from market.models import Price


def run():
    Price.objects.all().delete()
    Price.objects.create(price=Decimal('0.01'), name='Tier 1')
