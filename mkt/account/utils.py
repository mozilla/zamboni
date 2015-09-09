import mkt
from mkt.constants import apps
from mkt.site.models import manual_order
from mkt.site.utils import paginate
from mkt.webapps.models import Webapp


def purchase_list(request, user):
    # Return all apps that the user has a contribution for as well as all apps
    # they have installed.
    def get_ids(qs):
        return list(qs.order_by('-id').values_list('addon_id', flat=True))

    contributed_apps_ids = get_ids(user.contribution_set.filter(type__in=[
        mkt.CONTRIB_PURCHASE, mkt.CONTRIB_REFUND, mkt.CONTRIB_CHARGEBACK]))

    installed_apps_ids = get_ids(user.installed_set.filter(install_type__in=[
        apps.INSTALL_TYPE_USER, apps.INSTALL_TYPE_DEVELOPER]).exclude(
        addon__in=contributed_apps_ids))

    addon_ids = contributed_apps_ids + installed_apps_ids
    qs = Webapp.objects.filter(id__in=addon_ids)
    products = paginate(request, manual_order(qs, addon_ids), count=qs.count())
    return products
