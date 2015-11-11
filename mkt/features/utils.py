from mkt.constants.features import FeatureProfile


def load_feature_profile(request):
    """
    Adds a `feature_profile` on the request object if one is present and the
    dev parameter is either firefoxos or android.

    Does nothing if one was already set.
    """
    if hasattr(request, 'feature_profile'):
        return
    profile = None
    if request.GET.get('dev') in ('firefoxos', 'firefoxos+mobile',
                                  'firefoxos+tv', 'android'):
        sig = request.GET.get('pro')
        if sig:
            try:
                profile = FeatureProfile.from_signature(sig)
            except ValueError:
                pass
    request.feature_profile = profile
