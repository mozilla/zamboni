from datetime import datetime

import mkt

from aesfield.field import AESField


class FrozenAPIAccess(mkt.site.models.ModelBase):
    secret = AESField(max_length=255, aes_key='api:access:secret')

    class Meta:
        db_table = 'api_access'


def run():
    for access in FrozenAPIAccess.objects.all():
        access.secret = str(access.secret)
        if not access.created:
            access.created = datetime.now()
        access.save()
