import logging
from datetime import timedelta

from django import forms
from django.forms import widgets

import happyforms
from tower import ugettext as _
from tower import ugettext_lazy as _lazy

import mkt
from mkt.api.forms import CustomNullBooleanSelect
from mkt.reviewers.models import CannedResponse
from mkt.reviewers.utils import ReviewHelper
from mkt.search.forms import ApiSearchForm, SimpleSearchForm
from mkt.webapps.models import AddonDeviceType


log = logging.getLogger('z.reviewers.forms')

# We set 'any' here since we need to default this field
# to PUBLIC if not specified for consumer pages.
STATUS_CHOICES = [('any', _lazy(u'Any Status'))]
for status in mkt.WEBAPPS_UNLISTED_STATUSES + mkt.LISTED_STATUSES:
    STATUS_CHOICES.append((mkt.STATUS_CHOICES_API[status],
                           mkt.STATUS_CHOICES[status]))

MODERATE_ACTION_FILTERS = (('', ''), ('approved', _lazy(u'Approved reviews')),
                           ('deleted', _lazy(u'Deleted reviews')))

MODERATE_ACTION_DICT = {'approved': mkt.LOG.APPROVE_REVIEW,
                        'deleted': mkt.LOG.DELETE_REVIEW}

COMBINED_DEVICE_CHOICES = [('', _lazy(u'Any Device'))] + [
    (dev.api_name, dev.name) for dev in mkt.DEVICE_TYPE_LIST]


class ModerateLogForm(happyforms.Form):
    start = forms.DateField(required=False,
                            label=_lazy(u'View entries between'))
    end = forms.DateField(required=False,
                          label=_lazy(u'and'))
    search = forms.ChoiceField(required=False, choices=MODERATE_ACTION_FILTERS,
                               label=_lazy(u'Filter by type/action'))

    def clean(self):
        data = self.cleaned_data
        # We want this to be inclusive of the end date.
        if 'end' in data and data['end']:
            data['end'] += timedelta(days=1)

        if 'search' in data and data['search']:
            data['search'] = MODERATE_ACTION_DICT[data['search']]
        return data


class ModerateLogDetailForm(happyforms.Form):
    action = forms.CharField(
        required=True,
        widget=forms.HiddenInput(attrs={'value': 'undelete', }))


class ReviewLogForm(happyforms.Form):
    start = forms.DateField(required=False,
                            label=_lazy(u'View entries between'))
    end = forms.DateField(required=False, label=_lazy(u'and'))
    search = forms.CharField(required=False, label=_lazy(u'containing'))

    def __init__(self, *args, **kw):
        super(ReviewLogForm, self).__init__(*args, **kw)

        # L10n: start, as in "start date"
        self.fields['start'].widget.attrs = {'placeholder': _('start'),
                                             'size': 10}

        # L10n: end, as in "end date"
        self.fields['end'].widget.attrs = {'size': 10, 'placeholder': _('end')}

        self.fields['search'].widget.attrs = {
            # L10n: Descript of what can be searched for.
            'placeholder': _lazy(u'app, reviewer, or comment'),
            'size': 30}

    def clean(self):
        data = self.cleaned_data
        # We want this to be inclusive of the end date.
        if 'end' in data and data['end']:
            data['end'] += timedelta(days=1)

        return data


class NonValidatingChoiceField(forms.ChoiceField):
    """A ChoiceField that doesn't validate."""

    def validate(self, value):
        pass


class TestedOnForm(happyforms.Form):
    device_type = NonValidatingChoiceField(
        choices=([('', 'Choose...')] +
                 [(v.name, v.name) for _, v in mkt.DEVICE_TYPES.items()]),
        label=_lazy(u'Device Type:'), required=False)
    device = forms.CharField(required=False, label=_lazy(u'Device:'))
    version = forms.CharField(required=False, label=_lazy(u'Firefox Version:'))


TestedOnFormSet = forms.formsets.formset_factory(TestedOnForm)


class MOTDForm(happyforms.Form):
    motd = forms.CharField(required=True, widget=widgets.Textarea())


class ReviewAppForm(happyforms.Form):
    comments = forms.CharField(widget=forms.Textarea(),
                               label=_lazy(u'Comments:'))
    canned_response = NonValidatingChoiceField(required=False)
    action = forms.ChoiceField(widget=forms.RadioSelect())
    device_override = forms.TypedMultipleChoiceField(
        choices=[(k, v.name) for k, v in mkt.DEVICE_TYPES.items()],
        coerce=int, label=_lazy(u'Device Type Override:'),
        widget=forms.CheckboxSelectMultiple, required=False)
    is_tarako = forms.BooleanField(
        required=False, label=_lazy(u'This app works on Tarako devices.'))

    def __init__(self, *args, **kw):
        self.helper = kw.pop('helper')
        super(ReviewAppForm, self).__init__(*args, **kw)

        # We're starting with an empty one, which will be hidden via CSS.
        canned_choices = [['', [('', _('Choose a canned response...'))]]]

        responses = CannedResponse.objects.all()

        # Loop through the actions.
        for k, action in self.helper.actions.iteritems():
            action_choices = [[c.response, c.name] for c in responses
                              if c.sort_group and k in c.sort_group.split(',')]

            # Add the group of responses to the canned_choices array.
            if action_choices:
                canned_choices.append([action['label'], action_choices])

        # Now, add everything not in a group.
        for r in responses:
            if not r.sort_group:
                canned_choices.append([r.response, r.name])

        self.fields['canned_response'].choices = canned_choices
        self.fields['action'].choices = [(k, v['label']) for k, v
                                         in self.helper.actions.items()]
        device_types = AddonDeviceType.objects.filter(
            addon=self.helper.addon).values_list('device_type', flat=True)
        if device_types:
            self.initial['device_override'] = device_types

        self.initial['is_tarako'] = (
            self.helper.addon.tags.filter(tag_text='tarako').exists())

    def is_valid(self):
        result = super(ReviewAppForm, self).is_valid()
        if result:
            self.helper.set_data(self.cleaned_data)
        return result


def get_review_form(data, files, request=None, addon=None, version=None,
                    attachment_formset=None, testedon_formset=None):
    helper = ReviewHelper(request=request, addon=addon, version=version,
                          attachment_formset=attachment_formset,
                          testedon_formset=testedon_formset)
    return ReviewAppForm(data=data, files=files, helper=helper)


def _search_form_status(cleaned_data):
        status = cleaned_data['status']
        if status == 'any':
            return None

        return mkt.STATUS_CHOICES_API_LOOKUP.get(status, mkt.STATUS_PENDING)


class ApiReviewersSearchForm(ApiSearchForm):
    status = forms.ChoiceField(required=False, choices=STATUS_CHOICES,
                               label=_lazy(u'Status'))
    has_editor_comment = forms.NullBooleanField(
        required=False,
        label=_lazy(u'Has Editor Comment'),
        widget=CustomNullBooleanSelect)
    has_info_request = forms.NullBooleanField(
        required=False,
        label=_lazy(u'More Info Requested'),
        widget=CustomNullBooleanSelect)
    is_escalated = forms.NullBooleanField(
        required=False,
        label=_lazy(u'Escalated'),
        widget=CustomNullBooleanSelect)
    is_tarako = forms.NullBooleanField(
        required=False,
        label=_lazy(u'Tarako-ready'),
        widget=CustomNullBooleanSelect)
    dev_and_device = forms.ChoiceField(
        required=False, choices=COMBINED_DEVICE_CHOICES,
        label=_lazy(u'Device'))

    def __init__(self, *args, **kwargs):
        super(ApiReviewersSearchForm, self).__init__(*args, **kwargs)

        # Mobile form, to render, expects choices from the Django field.
        BOOL_CHOICES = ((u'', _lazy('Unknown')),
                        (u'true', _lazy('Yes')),
                        (u'false', _lazy('No')))
        for field_name, field in self.fields.iteritems():
            if isinstance(field, forms.NullBooleanField):
                self.fields[field_name].choices = BOOL_CHOICES

    def clean_status(self):
        return _search_form_status(self.cleaned_data)

    def clean(self):
        # Transform dev_and_device into the separate dev/device parameters.
        # We then call super() so that it gets transformed into ids that ES
        # will accept.
        dev_and_device = self.cleaned_data.pop('dev_and_device', '').split('+')
        self.cleaned_data['dev'] = dev_and_device[0]
        if len(dev_and_device) > 1:
            self.cleaned_data['device'] = dev_and_device[1]

        return super(ApiReviewersSearchForm, self).clean()


class ReviewersWebsiteSearchForm(SimpleSearchForm):
    status = forms.ChoiceField(required=False, choices=STATUS_CHOICES,
                               label=_lazy(u'Status'))

    def clean_status(self):
        return _search_form_status(self.cleaned_data)


class ApproveRegionForm(happyforms.Form):
    """TODO: Use a DRF serializer."""
    approve = forms.BooleanField(required=False)

    def __init__(self, *args, **kw):
        self.app = kw.pop('app')
        self.region = kw.pop('region')
        super(ApproveRegionForm, self).__init__(*args, **kw)

    def save(self):
        approved = self.cleaned_data['approve']

        if approved:
            status = mkt.STATUS_PUBLIC
            # Make it public in the previously excluded region.
            self.app.addonexcludedregion.filter(
                region=self.region.id).delete()
        else:
            status = mkt.STATUS_REJECTED

        value, changed = self.app.geodata.set_status(
            self.region, status, save=True)

        if changed:
            self.app.save()
