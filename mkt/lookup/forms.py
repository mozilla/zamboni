import os

from django import forms
from django.conf import settings

import happyforms
from tower import ugettext_lazy as _lazy

import mkt
from mkt.constants.base import PROMO_IMG_MINIMUMS
from mkt.developers.tasks import resize_promo_imgs
from mkt.developers.utils import check_upload
from mkt.site.utils import remove_promo_imgs
from mkt.webapps.models import Webapp


STATUS_CHOICES = []
for status in mkt.STATUS_CHOICES:
    STATUS_CHOICES.append((mkt.STATUS_CHOICES_API[status],
                           mkt.STATUS_CHOICES[status]))

FILE_STATUS_CHOICES = []
for status in mkt.MKT_STATUS_FILE_CHOICES:
    FILE_STATUS_CHOICES.append((mkt.STATUS_CHOICES_API[status],
                                mkt.MKT_STATUS_FILE_CHOICES[status]))


class NoAutoCompleteChoiceField(forms.ChoiceField):
    def widget_attrs(self, widget):
        attrs = super(NoAutoCompleteChoiceField, self).widget_attrs(widget)
        attrs['autocomplete'] = 'off'
        return attrs


class TransactionSearchForm(happyforms.Form):
    q = forms.CharField(label=_lazy(u'Transaction Lookup'))
    label_suffix = ''


class TransactionRefundForm(happyforms.Form):
    # A manual refund is one that does not use the payment providers API
    # but has been processed manually.
    manual = forms.BooleanField(
        label=_lazy(u'Process a manual refund'),
        required=False)
    refund_reason = forms.CharField(
        label=_lazy(u'Enter refund details to refund transaction'),
        widget=forms.Textarea(attrs={'rows': 4}))
    fake = forms.ChoiceField(
        choices=(('OK', 'OK'), ('PENDING', 'Pending'), ('INVALID', 'Invalid')))

    def __init__(self, *args, **kw):
        super(TransactionRefundForm, self).__init__(*args, **kw)
        if not settings.BANGO_FAKE_REFUNDS:
            del self.fields['fake']


class DeleteUserForm(happyforms.Form):
    delete_reason = forms.CharField(
        label=_lazy(u'Reason for Deletion'),
        widget=forms.Textarea(attrs={'rows': 2}))


class APIStatusForm(happyforms.Form):
    status = NoAutoCompleteChoiceField(
        required=False, choices=STATUS_CHOICES, label=_lazy(u'Status'))


class APIFileStatusForm(happyforms.Form):
    status = NoAutoCompleteChoiceField(
        required=False, choices=FILE_STATUS_CHOICES, label=_lazy(u'Status'))


class PromoImgForm(happyforms.Form):
    promo_img = forms.ImageField(
        label=_lazy(u'Promo Image'),
        help_text=_lazy(u'Minimum size: {0}x{1}').format(*PROMO_IMG_MINIMUMS))

    class Meta:
        model = Webapp

    def save(self, obj, commit=True):
        upload_type = 'promo_img'

        if upload_type in self.cleaned_data:
            errors, upload_hash = check_upload(
                self.cleaned_data[upload_type], upload_type,
                self.cleaned_data[upload_type].content_type)

            if errors:
                raise forms.ValidationError(errors)

            upload_path = os.path.join(settings.TMP_PATH, upload_type,
                                       upload_hash)

            dirname = obj.get_promo_img_dir()
            destination = os.path.join(dirname, '%s' % obj.id)

            remove_promo_imgs(destination)
            resize_promo_imgs.delay(upload_path, destination,
                                    mkt.PROMO_IMG_SIZES, set_modified_on=[obj])
