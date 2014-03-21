from mkt.constants.features import FeatureProfile


def get_feature_profile(request):
    profile = None
    platforms = ('firefoxos', 'android')
    if (request.GET.get('dev') in platforms or
        request.GET.get('platform') in platforms):
        sig = request.GET.get('pro')
        if sig:
            try:
                profile = FeatureProfile.from_signature(sig)
            except ValueError:
                pass
    return profile
