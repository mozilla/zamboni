from django.utils.translation import ugettext_lazy as _


INSTALL_TYPE_USER = 0
INSTALL_TYPE_REVIEWER = 1
INSTALL_TYPE_DEVELOPER = 2

INSTALL_TYPES = {
    INSTALL_TYPE_USER: _('User'),
    INSTALL_TYPE_REVIEWER: _('Reviewer'),
    INSTALL_TYPE_DEVELOPER: _('Developer')
}

MANIFEST_CONTENT_TYPE = 'application/x-web-app-manifest+json; charset=utf-8'
