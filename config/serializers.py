from rest_framework import serializers


class VersionedMutationSerializer(serializers.Serializer):
    expectedVersion = serializers.IntegerField(
        required=True,
        min_value=1,
    )