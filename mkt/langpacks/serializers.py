from rest_framework import exceptions, serializers

from mkt.files.models import FileUpload
from mkt.langpacks.models import LangPack


class LangPackUploadSerializer(serializers.Serializer):
    upload = serializers.CharField(required=True)

    def validate_upload(self, attrs, source):
        request = self.context['request']

        try:
            upload = FileUpload.objects.get(uuid=attrs[source],
                                            user=request.user)
        except FileUpload.DoesNotExist:
            raise serializers.ValidationError('No upload found.')
        if not upload.valid:
            raise serializers.ValidationError('Upload not valid.')

        # Override upload field with our FileUpload instance.
        attrs[source] = upload
        return attrs

    @property
    def data(self):
        return LangPackSerializer(self.object).data

    def save(self, **kwargs):
        # Never let save() happen here - We do it earlier, when restoring the
        # object - That's how the from_upload() static method on the model
        # works.
        return self.object

    def restore_object(self, attrs, instance=None):
        # FIXME: make updating existing LangPack instance work (i.e.
        # make sure instance/self.object/obj is correct).
        try:
            return LangPack.from_upload(attrs['upload'], instance=instance)
        except serializers.ValidationError, e:
            raise exceptions.ParseError(e.messages)


class LangPackSerializer(serializers.ModelSerializer):
    # Everything except "active" is read-only - the only way to update the
    # other fields is through LangPackUploadSerializer, since the manifest
    # is the source of truth. DRF has read_only_fields to do that, but we
    # want to be stricter and throw 400 errors if we encounter any of the
    # read-only fields.
    allowed_fields = ('active',)

    class Meta:
        model = LangPack

    def validate(self, attrs):
        errors = {}
        for key in attrs:
            if key not in self.allowed_fields:
                errors[key] = ['This field is read-only.']
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
