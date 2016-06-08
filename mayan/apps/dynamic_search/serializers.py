from __future__ import unicode_literals

from rest_framework import serializers

from .models import RecentSearch
from documents.models import Document


class RecentSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecentSearch
        read_only_fields = ('user', 'query', 'datetime_created', 'hits')


class SearchSerializer(serializers.Serializer):
    results = serializers.CharField()


class DocumentIdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ('id', 'label')
