import datetime
import decimal
import os
import StringIO

from django.conf import settings
from django.utils import six

import commonware.log
import defusedxml.ElementTree as etree
from jinja2 import Environment, FileSystemLoader
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser, BaseParser

import mkt.constants.iarc_mappings as mappings
from mkt.constants import ratingsbodies
from mkt.site.helpers import strip_controls
from mkt.translations.utils import no_translation

log = commonware.log.getLogger('z.iarc')


root = os.path.join(settings.ROOT, 'lib', 'iarc')
env = Environment(loader=FileSystemLoader(os.path.join(root, 'templates')))
env.finalize = lambda x: strip_controls(x)


def render_xml(template, context):
    """
    Renders an XML template given a dict of the context.

    This also strips control characters before encoding.

    """
    # All XML passed requires a password. Let's add it to the context.
    context['password'] = settings.IARC_PASSWORD
    context['platform'] = settings.IARC_PLATFORM

    template = env.get_template(template)
    return template.render(context)


def get_iarc_app_title(app):
    """Delocalized app name."""
    from mkt.webapps.models import Webapp

    with no_translation(app.default_locale):
        delocalized_app = Webapp.with_deleted.get(pk=app.pk)

    return unicode(delocalized_app.name)


class IARC_Parser(object):
    """
    Base class for IARC XML and JSON parsers.
    """

    def _process_iarc_items(self, data):
        """
        Looks for IARC keys ('interactive_elements' or keys starting with
        'rating_' or 'descriptors_') and trades them for a 'ratings' dictionary
        or descriptor and interactive lists.

        """
        rows = []  # New data object we'll return.

        for row in data:
            d = {}
            ratings = {}
            descriptors = []
            interactives = []

            for k, v in row.items():
                # Get ratings body constant.
                body = mappings.BODIES.get(k.split('_')[-1].lower(),
                                           ratingsbodies.GENERIC)

                if k == 'rating_system':
                    # This key is used in the Get_Rating_Changes API.
                    d[k] = mappings.BODIES.get(v.lower(),
                                               ratingsbodies.GENERIC)

                elif k == 'interactive_elements':
                    for interact in [s.strip() for s in v.split(',') if s]:
                        key = mappings.INTERACTIVES.get(interact)
                        if key:
                            interactives.append(key)
                        else:
                            log.error('Rating interactive %s DNE' % interact)

                elif k.startswith('rating_'):
                    ratings[body] = mappings.RATINGS[body.id].get(
                        v, mappings.RATINGS[body.id]['default'])

                elif k.startswith('descriptors_'):
                    for desc in [s.strip() for s in v.split(',') if s]:
                        key = mappings.DESCS[body.id].get(desc)
                        if key:
                            descriptors.append(key)
                        else:
                            log.error('Rating descriptor %s DNE' % desc)

                else:
                    d[k] = v

            if ratings:
                d['ratings'] = ratings
            if descriptors:
                d['descriptors'] = descriptors
            if interactives:
                d['interactives'] = interactives

            rows.append(d)

        return rows


# From django-rest-framework 2.x.
class XMLParser(BaseParser):
    """
    XML parser.
    """

    media_type = 'application/xml'

    def parse(self, stream, media_type=None, parser_context=None):
        """
        Parses the incoming bytestream as XML and returns the resulting data.
        """
        assert etree, 'XMLParser requires defusedxml to be installed'

        parser_context = parser_context or {}
        encoding = parser_context.get('encoding', settings.DEFAULT_CHARSET)
        parser = etree.DefusedXMLParser(encoding=encoding)
        try:
            tree = etree.parse(stream, parser=parser, forbid_dtd=True)
        except (etree.ParseError, ValueError) as exc:
            raise ParseError('XML parse error - %s' % six.text_type(exc))
        data = self._xml_convert(tree.getroot())

        return data

    def _xml_convert(self, element):
        """
        convert the xml `element` into the corresponding python object
        """

        children = list(element)

        if len(children) == 0:
            return self._type_convert(element.text)
        else:
            # if the 1st child tag is list-item means all children are list-itm
            if children[0].tag == "list-item":
                data = []
                for child in children:
                    data.append(self._xml_convert(child))
            else:
                data = {}
                for child in children:
                    data[child.tag] = self._xml_convert(child)

            return data

    def _type_convert(self, value):
        """
        Converts the value returned by the XMl parse into the equivalent
        Python type
        """
        if value is None:
            return value

        try:
            return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return decimal.Decimal(value)
        except decimal.InvalidOperation:
            pass

        return value


class IARC_XML_Parser(XMLParser, IARC_Parser):
    """
    Custom XML processor for IARC whack XML that defines all content in XML
    attributes with no tag content and all tags are named the same. This builds
    a dict using the "NAME" and "VALUE" attributes.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        """
        Parses the incoming bytestream as XML and returns the resulting data.
        """
        data = super(IARC_XML_Parser, self).parse(stream, media_type,
                                                  parser_context)

        # Process ratings, descriptors, interactives.
        data = self._process_iarc_items(data)

        # If it's a list, it had one or more "ROW" tags.
        if isinstance(data, list):
            data = {'rows': data}

        return data

    def parse_string(self, string):
        # WARNING: Ugly hack.
        #
        # IARC XML is utf-8 encoded yet the XML has a utf-16 header. Python
        # correctly reports the encoding mismatch and raises an error. So we
        # replace it here to make things work.
        string = string.replace('encoding="utf-16"', 'encoding="utf-8"')
        return self.parse(StringIO.StringIO(string))

    def _xml_convert(self, element):
        """
        Convert the xml `element` into the corresponding Python object.
        """
        children = list(element)

        if len(children) == 0:
            return self._type_convert(element.get('VALUE', ''))
        else:
            if children[0].tag == 'ROW':
                data = []
                for child in children:
                    data.append(self._xml_convert(child))
            else:
                data = {}
                for child in children:
                    data[child.get('NAME',
                                   child.tag)] = self._xml_convert(child)

        return data


class IARC_JSON_Parser(JSONParser, IARC_Parser):
    """
    JSON Parser to handle IARC's JSON format.
    """
    def parse(self, stream, media_type=None, parser_context=None):
        data = super(IARC_JSON_Parser, self).parse(stream, media_type,
                                                   parser_context)
        data = self._convert(data)
        data = self._process_iarc_items(data)

        return data

    def _convert(self, data):
        """
        Converts JSON that looks like::

            {
                "NAME": "token",
                "TYPE": "string",
                "VALUE": "AB12CD3"
            }

        Into something more normal that looks like this::

            {
                "token": "AB12CD3"
            }

        """
        d = {}
        for f in data['ROW']['FIELD']:
            d[f['NAME']] = f['VALUE']

        # Return a list to match the parsed XML.
        return [d]
