from rest_framework.filters import DjangoFilterBackend


class MktFilterBackend(DjangoFilterBackend):

    def munge_params(self, filter_munge, params):
        """
        Cast some more things as truthful.
        """
        for k in filter_munge:
            if k in params and params[k] in ['true', '1']:
                params[k] = 'True'
            if k in params and params[k] in ['false', '0']:
                params[k] = 'False'

        return params

    def filter_queryset(self, request, queryset, view):
        """
        Overriding DRF in order to munging the incoming params.

        It will only munge fields that are in the filter_munge tuple on the
        view, other fields will be untouched.
        """
        filter_class = self.get_filter_class(view, queryset)
        filter_munge = getattr(view, 'filter_munge', ())
        params = self.munge_params(filter_munge, request.query_params.copy())
        if filter_class:
            return filter_class(params, queryset=queryset).qs

        return queryset
