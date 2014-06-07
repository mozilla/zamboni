from django.contrib import admin

from mkt.prices.models import Price, PriceCurrency

admin.site.register(Price)
admin.site.register(PriceCurrency)
