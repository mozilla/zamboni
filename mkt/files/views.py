from urlparse import urljoin

from django import http, shortcuts
from django.conf import settings
from django.core.urlresolvers import reverse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import condition

import commonware.log
from cache_nuggets.lib import Message, Token
from jingo.helpers import urlparams
from tower import ugettext as _

from mkt.access import acl
from mkt.files import forms
from mkt.files.decorators import (compare_webapp_file_view, etag,
                                  last_modified, webapp_file_view,
                                  webapp_file_view_token)
from mkt.files.tasks import extract_file
from mkt.site.decorators import json_view
from mkt.site.utils import get_file_response


log = commonware.log.getLogger('z.addons')


def setup_viewer(request, file_obj):
    data = {'file': file_obj,
            'version': file_obj.version,
            'addon': file_obj.version.addon,
            'status': False,
            'selected': {},
            'validate_url': ''}

    if (acl.check_reviewer(request) or
        acl.check_addon_ownership(request, file_obj.version.addon,
                                  viewer=True, ignore_disabled=True)):
        data['validate_url'] = reverse(
            'mkt.developers.apps.json_file_validation',
            args=[file_obj.version.addon.app_slug, file_obj.id])

    if acl.check_reviewer(request):
        data['file_link'] = {'text': _('Back to review'),
                             'url': reverse('reviewers.apps.review',
                                            args=[data['addon'].app_slug])}
    else:
        data['file_link'] = {
            'text': _('Back to app'),
            'url': reverse('detail', args=[data['addon'].pk])
        }
    return data


@never_cache
@json_view
@webapp_file_view
def poll(request, viewer):
    return {'status': viewer.is_extracted(),
            'msg': [Message('file-viewer:%s' % viewer).get(delete=True)]}


def check_compare_form(request, form):
    if request.method == 'POST':
        if form.is_valid():
            left = form.cleaned_data['left']
            right = form.cleaned_data.get('right')
            if right:
                url = reverse('mkt.files.compare', args=[left, right])
            else:
                url = reverse('mkt.files.list', args=[left])
        else:
            url = request.path
        return shortcuts.redirect(url)


@csrf_exempt
@webapp_file_view
@condition(etag_func=etag, last_modified_func=last_modified)
def browse(request, viewer, key=None, type_='file'):
    form = forms.FileCompareForm(request.POST or None, addon=viewer.addon,
                                 initial={'left': viewer.file})
    response = check_compare_form(request, form)
    if response:
        return response

    data = setup_viewer(request, viewer.file)
    data['viewer'] = viewer
    data['poll_url'] = reverse('mkt.files.poll', args=[viewer.file.id])
    data['form'] = form

    if not viewer.is_extracted():
        extract_file(viewer.file.id)

    if viewer.is_extracted():
        data.update({'status': True, 'files': viewer.get_files()})
        key = viewer.get_default(key)
        if key not in data['files']:
            raise http.Http404

        viewer.select(key)
        data['key'] = key

        binary = viewer.is_binary()
        if (not viewer.is_directory() and
                (not binary or binary != 'image')):
            data['content'] = viewer.read_file()

    else:
        extract_file.delay(viewer.file.id)

    tmpl = 'content' if type_ == 'fragment' else 'viewer'
    return render(request, 'fileviewer/%s.html' % tmpl, data)


@never_cache
@compare_webapp_file_view
@json_view
def compare_poll(request, diff):
    msgs = []
    for f in (diff.left, diff.right):
        m = Message('file-viewer:%s' % f).get(delete=True)
        if m:
            msgs.append(m)
    return {'status': diff.is_extracted(), 'msg': msgs}


@csrf_exempt
@compare_webapp_file_view
@condition(etag_func=etag, last_modified_func=last_modified)
def compare(request, diff, key=None, type_='file'):
    form = forms.FileCompareForm(request.POST or None, addon=diff.addon,
                                 initial={'left': diff.left.file,
                                          'right': diff.right.file})
    response = check_compare_form(request, form)
    if response:
        return response

    data = setup_viewer(request, diff.left.file)
    data['diff'] = diff
    data['poll_url'] = reverse('mkt.files.compare.poll',
                               args=[diff.left.file.id,
                                     diff.right.file.id])
    data['form'] = form

    if not diff.is_extracted():
        extract_file(diff.left.file.id)
        extract_file(diff.right.file.id)

    if diff.is_extracted():
        data.update({'status': True,
                     'files': diff.get_files(),
                     'files_deleted': diff.get_deleted_files()})
        key = diff.left.get_default(key)
        if key not in data['files'] and key not in data['files_deleted']:
            raise http.Http404

        diff.select(key)
        data['key'] = key
        if diff.is_diffable():
            data['left'], data['right'] = diff.read_file()

    else:
        extract_file.delay(diff.left.file.id)
        extract_file.delay(diff.right.file.id)

    tmpl = 'content' if type_ == 'fragment' else 'viewer'
    return render(request, 'fileviewer/%s.html' % tmpl, data)


@webapp_file_view
def redirect(request, viewer, key):
    new = Token(data=[viewer.file.id, key])
    new.save()
    url = urljoin(settings.STATIC_URL,
                  reverse('mkt.files.serve', args=[viewer, key]))
    url = urlparams(url, token=new.token)
    return http.HttpResponseRedirect(url)


@webapp_file_view_token
def serve(request, viewer, key):
    """
    This is to serve files off of st.a.m.o, not standard a.m.o. For this we
    use token based authentication.
    """
    files = viewer.get_files()
    obj = files.get(key)
    if not obj:
        log.error(u'Couldn\'t find %s in %s (%d entries) for file %s' %
                  (key, files.keys()[:10], len(files.keys()), viewer.file.id))
        raise http.Http404()
    return get_file_response(request, obj['full'],
                             content_type=obj['mimetype'])
