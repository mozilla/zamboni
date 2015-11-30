from rest_framework.exceptions import ParseError

from mkt.constants.iarc_mappings import (BODIES, DESCS_V2, INTERACTIVES_V2,
                                         RATINGS)
from mkt.site.utils import cached_property


class IARCV2RatingListSerializer(object):
    """Class that is used to de-serialize json sent/received from IARC to our
    ratings/descriptors/interactive model instances for a given app.

    Not a true rest-framework serializer, because there is little point: it
    has to deal with several instances for each model, and we don't care about
    serializing back to json."""

    def __init__(self, instance=None, data=None):
        self.instance = instance
        self.data = data

    @cached_property
    def validated_data(self):
        validated_data = {
            'descriptors': set(),
            'interactives': set(),
            'ratings': {},

        }
        rating_list = self.data.get('RatingList')
        if not rating_list:
            return None

        for raw_info in rating_list:
            body = BODIES.get(raw_info['RatingAuthorityShortText'].lower())
            if not body:
                # Ignore unknown rating bodies.
                continue
            validated_data['ratings'][body] = RATINGS[body.id].get(
                raw_info['AgeRatingText'], RATINGS[body.id]['default'])

            for raw_descriptor in raw_info['DescriptorList']:
                descriptor = DESCS_V2[body.id].get(raw_descriptor[
                    'DescriptorText'])
                if descriptor:
                    validated_data['descriptors'].add(descriptor)

            for raw_interactive in raw_info['InteractiveElementList']:
                interactive = INTERACTIVES_V2.get(raw_interactive[
                    'InteractiveElementText'])
                if interactive:
                    validated_data['interactives'].add(interactive)

        return validated_data

    def is_valid(self):
        return bool(self.validated_data)

    def save(self):
        if not self.instance:
            raise ValueError('Can not save without an instance.')

        if not self.is_valid():
            raise ParseError('Can not save with invalid data.')

        self.instance.set_descriptors(self.validated_data['descriptors'])
        self.instance.set_interactives(self.validated_data['interactives'])
        self.instance.set_content_ratings(self.validated_data['ratings'])
