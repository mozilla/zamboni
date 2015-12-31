import logging
import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from mkt.commonplace.models import DeployBuildId
from mkt.site.storage_utils import local_storage


log = logging.getLogger('commonplace')


class Command(BaseCommand):
    use_argparse = False

    def handle(self, *args, **kw):
        if len(args) < 1:
            sys.stdout.write('Pass repo name as arg (e.g., fireplace).\n')
            return

        repo = args[0]

        repo_build_id = DeployBuildId.objects.get_or_create(repo=repo)[0]
        old_build_id = repo_build_id.build_id

        if len(args) > 1:
            # Read the build ID from the second argument.
            repo_build_id.build_id = str(args[1])
        else:
            # Read the build ID from build_id.txt in the repository's root.
            build_id_path = os.path.join(
                settings.MEDIA_ROOT, repo, 'build_id.txt')
            with local_storage.open(build_id_path) as f:
                repo_build_id.build_id = f.read()

        # Save it.
        repo_build_id.save()
        print "Successfully changed %s's build_id from %s to %s in db\n" % (
            repo, old_build_id, repo_build_id.build_id
        )
