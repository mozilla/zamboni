import random

from mkt.constants.applications import DEVICE_TYPES
from mkt.constants.base import STATUS_PUBLIC
from mkt.websites.models import Website


dummy_text = ['ariel', 'callisto', 'charon', 'dione', 'earth', 'enceladus',
              'europa', 'ganymede', 'hyperion', 'iapetus', 'io', 'jupiter',
              'mars', 'mercury', 'mimas', 'miranda', 'moon', 'neptune',
              'nereid', 'oberon', 'phoebe', 'pluto', 'proteus', 'rhea',
              'saturn', 'sun', 'tethys', 'titan', 'titania', 'triton',
              'umbriel', 'uranus', 'venus']


def rand_text():
    """Generate random string for websites."""
    return '%s%d' % (random.choice(dummy_text), random.randrange(0, 9999))


def website_factory(**kwargs):
    text = rand_text()
    data = {
        'description': 'Description for %s' % text.capitalize(),
        'name': text.capitalize(),
        'short_name': text[:10].capitalize(),
        'status': STATUS_PUBLIC,
        'title': 'Title for %s' % text.capitalize(),
        'url': 'http://%s.example.com' % text,
        'mobile_url': 'http://mobile.%s.example.com' % text,
        'devices': DEVICE_TYPES.keys(),
    }
    data.update(kwargs)
    return Website.objects.create(**data)
