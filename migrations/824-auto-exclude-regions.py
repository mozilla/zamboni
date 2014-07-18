from mkt.constants import regions
from mkt.developers.cron import exclude_new_region


def run():
    exclude_new_region([
        regions.CR,
        regions.EC,
        regions.FR,
        regions.GT,
        regions.IT,
        regions.NI,
        regions.PA,
        regions.SV,
    ])
