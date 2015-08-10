import hashlib
import random

import pydenticon

from mkt.constants.carriers import CARRIER_CHOICE_DICT
from mkt.constants.regions import REGIONS_DICT
from mkt.feed.models import (FeedApp, FeedBrand, FeedBrandMembership,
                             FeedCollection, FeedCollectionMembership,
                             FeedItem, FeedShelf, FeedShelfMembership)
from mkt.site.storage_utils import public_storage
from mkt.webapps.fakedata import foreground, generate_apps
from mpconstants.collection_colors import COLLECTION_COLORS


dummy_text = 'foo bar baz blee zip zap cvan fizz buzz something'.split()


def rand_text(n=10):
    """Generate random string."""
    return ' '.join(random.choice(dummy_text) for i in xrange(n))


def shelf(apps, **kw):
    carrier = kw.get('carrier', random.choice(CARRIER_CHOICE_DICT.values()))
    region = REGIONS_DICT[kw.get('region', 'restofworld')].id
    sh = FeedShelf.objects.create(
        carrier=carrier.id,
        description=kw.get('description', 'shelf for ' + carrier.name),
        name=kw.get('name', '%s Op Shelf' % carrier.name),
        region=region)
    gen = pydenticon.Generator(8, 8, foreground=foreground)
    img = gen.generate(unicode(sh.name).encode('utf8'), 128, 128,
                       output_format='png')
    with public_storage.open(sh.image_path(''), 'wb') as f:
        f.write(img)
    with public_storage.open(sh.image_path('_landing'), 'wb') as f:
        f.write(img)
    image_hash = hashlib.md5(img).hexdigest()[:8]
    sh.update(slug=kw.get('slug', 'shelf-%d' % sh.pk),
              image_hash=image_hash,
              image_landing_hash=image_hash)

    for a in apps:
        FeedShelfMembership.objects.create(obj=sh, app=a)
    FeedItem.objects.create(item_type='shelf', shelf=sh, region=region)
    return sh


def brand(apps, type, **kw):
    region = REGIONS_DICT[kw.get('region', 'restofworld')].id
    br = FeedBrand.objects.create(
        layout=kw.get('layout', random.choice(['list', 'grid'])),
        slug='brand-',
        type=type)
    br.update(slug=kw.get('slug', 'brand-%d' % br.pk))
    for a in apps:
        FeedBrandMembership.objects.create(obj=br, app=a)
    FeedItem.objects.create(item_type='brand', brand=br, region=region)
    return br


def collection(apps, slug, background_image=True, **kw):
    region = REGIONS_DICT[kw.get('region', 'restofworld')].id
    colorname = kw.get('color', random.choice(COLLECTION_COLORS.keys()))
    co = FeedCollection.objects.create(
        type=kw.get('type', 'listing'),
        color=colorname,
        background_color=COLLECTION_COLORS[colorname],
        slug=slug,
        description=kw.get('description', ''))
    name = kw.get('name', 'Collection %s' % co.pk)
    if background_image:
        gen = pydenticon.Generator(8, 8, foreground=foreground)
        img = gen.generate(name, 128, 128,
                           output_format='png')
        with public_storage.open(co.image_path(''), 'wb') as f:
            f.write(img)
        image_hash = hashlib.md5(img).hexdigest()[:8]
    else:
        image_hash = None
    co.name = name
    co.image_hash = image_hash
    co.save()
    for a in apps:
        FeedCollectionMembership.objects.create(obj=co, app=a)
    FeedItem.objects.create(item_type='collection', collection=co,
                            region=region)
    return co


def app_item(a, type, **kw):
    region = REGIONS_DICT[kw.get('region', 'restofworld')].id
    colorname = kw.get('color', random.choice(COLLECTION_COLORS.keys()))
    gen = pydenticon.Generator(8, 8, foreground=foreground)
    img = gen.generate(a.app_slug, 128, 128,
                       output_format='png')
    ap = FeedApp.objects.create(
        app=a,
        description=kw.get('description', rand_text(12)),
        type=type,
        color=colorname,
        preview=kw.get('preview', None),
        pullquote_attribution=kw.get('pullquote_attribution', None),
        pullquote_rating=kw.get('pullquote_rating', None),
        pullquote_text=kw.get('pullquote_text', None),
        background_color=COLLECTION_COLORS[colorname],
        slug=kw.get('slug', 'feed-app-%d' % a.pk))
    with public_storage.open(ap.image_path(''), 'wb') as f:
        f.write(img)
        image_hash = hashlib.md5(img).hexdigest()[:8]
    ap.update(image_hash=image_hash)
    FeedItem.objects.create(item_type='app', app=ap, region=region)
    return ap


def generate_feed_data():
    apps = generate_apps(
        24, device_types=['desktop', 'mobile', 'tablet', 'firefoxos'])
    apps1, apps2, apps3, apps4 = apps[:6], apps[6:12], apps[12:18], apps[18:]
    shelf(apps1, slug='shelf', name='Shelf', description='')
    shelf(apps2, slug='shelf-desc', name='Shelf Description',
          description=rand_text())
    brand(apps1, 'hidden-gem', slug='brand-grid', layout='grid')
    brand(apps2, 'travel', slug='brand-list', layout='list')
    co = collection([], slug='grouped')
    co.add_app_grouped(apps1[0].pk, 'group 1')
    co.add_app_grouped(apps1[1].pk, 'group 1')
    co.add_app_grouped(apps1[2].pk, 'group 2')
    co.add_app_grouped(apps1[3].pk, 'group 2')
    co.add_app_grouped(apps1[4].pk, 'group 3')
    co.add_app_grouped(apps1[5].pk, 'group 3')
    collection(apps2, slug='coll-promo', type='promo', name='Coll Promo')
    collection(apps2, slug='coll-promo-desc', type='promo',
               name='Coll Promo Desc',
               description=rand_text(),
               background_image=False)

    collection(apps2, slug='coll-promo-bg', type='promo',
               description='', name='Coll Promo Background')
    collection(apps2, slug='coll-promo-bg-desc', type='promo',
               name='Coll Promo Background Desc',
               description=rand_text(),
               background_image=False)
    collection(apps3, slug='coll-listing', type='listing',
               name='Coll Listing')
    collection(apps3, slug='coll-listing-desc', type='listing',
               name='Coll Listing Desc',
               description=rand_text())
    app_item(apps4[0], type='icon', slug='feedapp-icon')
    app_item(apps4[1], type='image', slug='feedapp-image')
    app_item(apps4[2], type='description', slug='feedapp-description')
    app_item(apps4[3], type='quote', slug='feedapp-quote',
             pullquote_text='"%s"' % rand_text(12),
             pullquote_rating=4,
             pullquote_attribution="matt basta")
    app_item(apps4[4], type='preview', slug='feedapp-preview')
