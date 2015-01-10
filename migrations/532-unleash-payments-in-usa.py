import mkt
from mkt.webapps.models import AddonExcludedRegion


def run():
    """Unleash payments in USA."""
    (AddonExcludedRegion.objects
     .exclude(addon__premium_type=mkt.ADDON_FREE)
     .filter(region=mkt.regions.US.id).delete())
