from django import forms

import happyforms

from mkt.api.forms import SluggableModelChoiceField
from mkt.inapp.models import InAppProduct
from mkt.webapps.models import Webapp


class PrepareWebAppForm(happyforms.Form):
    app = SluggableModelChoiceField(queryset=Webapp.objects.valid(),
                                    sluggable_to_field_name='app_slug')


class PrepareInAppForm(happyforms.Form):
    inapp = forms.ModelChoiceField(queryset=InAppProduct.objects.all(),
                                   to_field_name='guid')

    def clean_inapp(self):
        inapp = self.cleaned_data['inapp']

        if not inapp.is_purchasable():
            raise forms.ValidationError(
                'Can not start a purchase on this inapp product.')

        return inapp


class FailureForm(happyforms.Form):
    url = forms.CharField()
    attempts = forms.IntegerField()
