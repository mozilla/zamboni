from mkt.constants import regions
from mkt.developers.cron import exclude_new_region, send_new_region_emails


def run():
    exclude_new_region([regions.BD])
    send_new_region_emails([regions.BD])
