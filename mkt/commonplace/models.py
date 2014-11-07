from django.db import models

from mkt.site.models import ModelBase


class DeployBuildId(ModelBase):
    """
    After deployments are completely finished to all the webheads, build IDs
    that are generated from our frontend builds (marketplace-gulp) and written
    to src/build_id.txt are stored in this table, keyed by repo.
    For each request to Commonplace's index.html, we'll do a lookup to make
    sure we have a proper build ID that matches the assets we have on every
    webhead.
    Bug 1083185 has all the information.
    """
    repo = models.CharField(max_length=40, unique=True)
    build_id = models.CharField(max_length=20, blank=True, default='')

    class Meta:
        db_table = 'deploy_build_id'
