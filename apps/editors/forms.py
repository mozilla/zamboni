import logging
from datetime import timedelta

from django import forms
from django.forms import widgets

import happyforms
from tower import ugettext as _, ugettext_lazy as _lazy


log = logging.getLogger('z.reviewers.forms')


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

        # L10n: Description of what can be searched for
        search_ph = _('add-on, editor or comment')
        self.fields['search'].widget.attrs = {'placeholder': search_ph,
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


class MOTDForm(happyforms.Form):
    motd = forms.CharField(required=True, widget=widgets.Textarea())
