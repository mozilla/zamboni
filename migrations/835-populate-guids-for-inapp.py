from mkt.inapp.models import InAppProduct


def run():
    for inapp in InAppProduct.objects.all():
        inapp.save()
