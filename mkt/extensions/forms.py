from django import forms


class ExtensionSearchForm(forms.Form):
    """Form used to clean up query parameters before sending them to
    ExtensionSearchFormFilter."""
    # Note: consider inheriting from mkt.search.forms.SimpleSearchForm later
    # when it starts sharing more fields with Webapps and Websites.
    author = forms.CharField(required=False)

    def clean_author(self):
        author = self.cleaned_data.get('author')
        if author:
            return author.lower().strip()
