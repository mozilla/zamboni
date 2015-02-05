import datetime
import hashlib
import itertools
import os
import json
import random
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from django.conf import settings

import pydenticon

import mkt
from mkt.constants.applications import DEVICE_TYPES
from mkt.constants.base import STATUS_CHOICES_API_LOOKUP
from mkt.constants.categories import CATEGORY_CHOICES
from mkt.developers.tasks import resize_preview, save_icon
from mkt.ratings.models import Review
from mkt.site.utils import slugify
from mkt.users.models import UserProfile
from mkt.webapps.models import AppManifest, Preview

adjectives = ['Exquisite', 'Delicious', 'Elegant', 'Swanky', 'Spicy',
              'Food Truck', 'Artisanal', 'Tasty']
nouns = ['Sandwich', 'Pizza', 'Curry', 'Pierogi', 'Sushi', 'Salad', 'Stew',
         'Pasta', 'Barbeque', 'Bacon', 'Pancake', 'Waffle', 'Chocolate',
         'Gyro', 'Cookie', 'Burrito', 'Pie']
fake_app_names = list(itertools.product(adjectives, nouns))[:-1]


def generate_app_data(num):
    repeats, tailsize = divmod(num, len(fake_app_names))
    if repeats:
        apps = fake_app_names[:]
        for i in range(repeats - 1):
            for a in fake_app_names:
                apps.append(a + (str(i + 1),))
        for a in fake_app_names[:tailsize]:
            apps.append(a + (str(i + 2),))
    else:
        apps = random.sample(fake_app_names, tailsize)
    # Let's have at least 3 apps in each category, if we can.
    if num < (len(CATEGORY_CHOICES) * 3):
        num_cats = max(num // 3, 1)
    else:
        num_cats = len(CATEGORY_CHOICES)
    catsize = num // num_cats
    ia = iter(apps)
    for cat_slug, cat_name in CATEGORY_CHOICES[:num_cats]:
        for n in range(catsize):
            appname = ' '.join(next(ia))
            yield (appname, cat_slug)
    for i, app in enumerate(ia):
        appname = ' '.join(app)
        cat_slug, cat_name = CATEGORY_CHOICES[i % len(CATEGORY_CHOICES)]
        yield (appname, cat_slug)

foreground = ["rgb(45,79,255)",
              "rgb(254,180,44)",
              "rgb(226,121,234)",
              "rgb(30,179,253)",
              "rgb(232,77,65)",
              "rgb(49,203,115)",
              "rgb(141,69,170)"]


def generate_icon(app):
    gen = pydenticon.Generator(8, 8, foreground=foreground)
    img = gen.generate(unicode(app.name).encode('utf8'), 128, 128,
                       output_format="png")
    save_icon(app, img)


def generate_previews(app, n=1):
    gen = pydenticon.Generator(8, 12, foreground=foreground,
                               digest=hashlib.sha512)
    for i in range(n):
        img = gen.generate(unicode(app.name).encode('utf8') + chr(i), 320, 480,
                           output_format="png")
        p = Preview.objects.create(addon=app, filetype="image/png",
                                   thumbtype="image/png",
                                   caption="screenshot " + str(i),
                                   position=i)
        f = tempfile.NamedTemporaryFile(suffix='.png')
        f.write(img)
        f.flush()
        resize_preview(f.name, p)


def generate_localized_names(name, n):
    prefixes = [('fr', u'fran\xe7ais'),
                ('es', u'espa\xf1ol'),
                ('ru', u'\u0420\u0443\u0441\u0441\u043a\u0438\u0439'),
                ('ja', u'\u65e5\u672c\u8a9e'),
                ('pt', u'portugu\xeas')]
    names = dict((lang, u'%s %s' % (prefix, name))
                 for lang, prefix in prefixes[:n])
    names['en-us'] = unicode(name)
    return names


def generate_ratings(app, num):
    for n in range(num):
        email = 'testuser%s@example.com' % (n,)
        user, _ = UserProfile.objects.get_or_create(
            username=email, email=email, source=mkt.LOGIN_SOURCE_UNKNOWN,
            display_name=email)
        Review.objects.create(
            addon=app, user=user, rating=random.randrange(0, 6),
            title="Test Review " + str(n), body="review text")
    app.update(total_reviews=num)


def generate_hosted_app(name, category):
    # Let's not make production code depend on stuff in the test package --
    # importing it only when called in local dev is fine.
    from mkt.site.tests import app_factory
    a = app_factory(categories=[category], name=name, complete=False,
                    rated=True)
    a.addondevicetype_set.create(device_type=DEVICE_TYPES.keys()[0])
    a.versions.latest().update(reviewed=datetime.datetime.now())
    generate_hosted_manifest(a)
    return a


def generate_hosted_manifest(app):
    data = {
        'name': unicode(app.name),
        'description': 'This app has been automatically generated',
        'version': '1.0',
        'icons': {
            '16': 'http://testmanifest.com/icon-16.png',
            '48': 'http://testmanifest.com/icon-48.png',
            '128': 'http://testmanifest.com/icon-128.png'
        },
        'installs_allowed_from': ['*'],
        'developer': {
            'name': 'Marketplace Team',
            'url': 'https://marketplace.firefox.com/credits'
        }
    }
    AppManifest.objects.create(
        version=app._latest_version, manifest=json.dumps(data))
    app.update(manifest_url='http://%s.testmanifest.com/manifest.webapp' %
               (slugify(unicode(app.name)),))


def generate_app_package(app, out, apptype, permissions, version='1.0',
                         num_locales=2):
    manifest = {
        'version': version.version,
        'name': unicode(app.name),
        'description': ('This packaged app has been automatically generated'
                        ' (version %s)' % (version.version,)),
        'icons': {
            '16': '/icons/16.png',
            '32': '/icons/32.png',
            '256': '/icons/256.png'
        },
        'developer': {
            'name': 'Marketplace Team',
            'url': 'https://marketplace.firefox.com/credits'
        },
        'installs_allowed_launch': ['*'],
        'from_path': 'index.html',
        'locales':  dict((lang, {
            'name': name,
            'description': 'This packaged app has been automatically generated'
        }) for lang, name in generate_localized_names(
            app.name, num_locales).items()),
        'permissions': dict(((k, {"description": k})
                             for k in permissions)),
        'default_locale': 'en',
        'orientation': 'landscape',
        'type': 'web' if apptype == 'packaged' else apptype,
        'fullscreen': 'true'
    }
    outz = ZipFile(file=out, mode='w', compression=ZIP_DEFLATED)
    try:
        for size in ('32', 'med'):
            outz.writestr(
                'icons/%s.png' % (size,),
                open(os.path.join(
                    settings.MEDIA_ROOT,
                    'img/app-icons/%s/generic.png' % (size,))).read())
        outz.writestr('script.js',
                      'document.onload=function() {alert("Hello!");};')
        outz.writestr(
            'index.html',
            '<title>Packaged app</title><script src="script.js"></script>'
            '<h1>Test packaged app</h1>')
        outz.writestr("manifest.webapp", json.dumps(manifest))
    finally:
        outz.close()
    AppManifest.objects.create(
        version=version, manifest=json.dumps(manifest))


def generate_packaged_app(name, apptype, category, permissions=(),
                          versions=(4,), num_locales=2, **kw):
    from mkt.site.tests import app_factory, version_factory
    now = datetime.datetime.now()
    app = app_factory(categories=[category], name=name, complete=False,
                      rated=True, is_packaged=True,
                      version_kw={'version': '1.0', 'status': versions[0],
                                  'reviewed': now})
    app.addondevicetype_set.create(device_type=DEVICE_TYPES.keys()[0])
    f = app.latest_version.all_files[0]
    f.update(filename=f.generate_filename())
    fp = os.path.join(app.latest_version.path_prefix, f.filename)
    try:
        os.makedirs(os.path.dirname(fp))
    except OSError:
        pass
    with open(fp, 'w') as out:
        generate_app_package(app, out, apptype, permissions=permissions,
                             version=app.latest_version,
                             num_locales=num_locales)
        for i, f_status in enumerate(versions[1:], 1):
            st = STATUS_CHOICES_API_LOOKUP[f_status]
            rtime = now + datetime.timedelta(i)
            v = version_factory(version="1." + str(i), addon=app,
                                reviewed=rtime, created=rtime,
                                file_kw={'status': st})
            generate_app_package(app, out, apptype, permissions, v,
                                 num_locales=num_locales)
        app.update_version()
    return app


def generate_apps(hosted=0, packaged=0, privileged=0, versions=(4,)):
    apps = generate_app_data(hosted + packaged + privileged)
    for i, (appname, cat_slug) in enumerate(apps):
        if i < privileged:
            app = generate_packaged_app(appname, 'privileged', cat_slug,
                                        versions=versions,
                                        permissions=['camera', 'storage'])
        elif i < (privileged + packaged):
            app = generate_packaged_app(appname, 'packaged', cat_slug,
                                        versions=versions)
        else:
            app = generate_hosted_app(appname, cat_slug)
        app.name = generate_localized_names(app.name, 2)
        generate_icon(app)
        generate_previews(app)
        generate_ratings(app, 5)


def generate_apps_from_specs(specs):
    for spec, (appname, cat_slug) in zip(specs, generate_app_data(len(specs))):
        generate_app_from_spec(appname, cat_slug, **spec)


def generate_app_from_spec(appname, cat_slug, type, status, num_previews=1,
                           num_ratings=1, num_locales=0, **spec):
    if type == 'hosted':
        app = generate_hosted_app(appname, cat_slug)
    else:
        app = generate_packaged_app(
            appname, type, cat_slug, **spec)
    generate_icon(app)
    generate_previews(app, num_previews)
    generate_ratings(app, num_ratings)
    app.name = generate_localized_names(app.name, num_locales)
    # Status has to be updated at the end because STATUS_DELETED apps can't
    # be saved.
    app.status = STATUS_CHOICES_API_LOOKUP[status]
    app.save()
    return app
