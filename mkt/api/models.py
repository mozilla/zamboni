import time

from django.db import models
from django.utils.crypto import get_random_string

from aesfield.field import AESField

from mkt.site.models import ModelBase
from mkt.users.models import UserProfile


REQUEST_TOKEN = 0
ACCESS_TOKEN = 1
TOKEN_TYPES = ((REQUEST_TOKEN, u'Request'), (ACCESS_TOKEN, u'Access'))


class Access(ModelBase):
    key = models.CharField(max_length=255, unique=True)
    secret = AESField(max_length=255, aes_key='api:access:secret')
    user = models.ForeignKey(UserProfile)
    redirect_uri = models.CharField(max_length=255)
    app_name = models.CharField(max_length=255)

    class Meta:
        db_table = 'api_access'

    @classmethod
    def create_for_user(cls, user):
        key = 'mkt:%s:%s:%s' % (
            user.pk,
            user.email,
            Access.objects.filter(user=user).count())
        return Access.objects.create(
            key=key,
            user=user,
            secret=get_random_string().encode('ascii'))


class Token(ModelBase):
    token_type = models.SmallIntegerField(choices=TOKEN_TYPES)
    creds = models.ForeignKey(Access)
    key = models.CharField(max_length=255)
    secret = models.CharField(max_length=255)
    timestamp = models.IntegerField()
    user = models.ForeignKey(UserProfile, null=True)
    verifier = models.CharField(max_length=255, null=True)

    class Meta:
        db_table = 'oauth_token'

    @classmethod
    def generate_new(cls, token_type, creds, user=None):
        return cls.objects.create(
            token_type=token_type,
            creds=creds,
            key=get_random_string(),
            secret=get_random_string(),
            timestamp=time.time(),
            verifier=(get_random_string()
                      if token_type == REQUEST_TOKEN else None),
            user=user)


class Nonce(ModelBase):
    nonce = models.CharField(max_length=128)
    timestamp = models.IntegerField()
    client_key = models.CharField(max_length=255)
    request_token = models.CharField(max_length=128, null=True)
    access_token = models.CharField(max_length=128, null=True)

    class Meta:
        db_table = 'oauth_nonce'
        unique_together = ('nonce', 'timestamp', 'client_key',
                           'request_token', 'access_token')
