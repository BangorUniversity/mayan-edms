from __future__ import unicode_literals

from rest_framework import generics
from rest_framework.exceptions import ParseError

from rest_api.filters import MayanObjectPermissionsFilter

from rest_api.permissions import MayanPermission

from .classes import SearchModel
from .models import RecentSearch
from .serializers import RecentSearchSerializer, SearchSerializer, DocumentIdSerializer

from documents.permissions import PERMISSION_DOCUMENT_VIEW

from documents.models import Document


class APIRecentSearchListView(generics.ListAPIView):
    """
    Returns a list of all the recent searches.
    """

    serializer_class = RecentSearchSerializer
    queryset = RecentSearch.objects.all()

    # TODO: Add filter_backend so that users can only see their own entries


class APIRecentSearchView(generics.RetrieveDestroyAPIView):
    """
    Returns the selected recent search details.
    """

    serializer_class = RecentSearchSerializer
    queryset = RecentSearch.objects.all()

    # TODO: Add filter_backend so that users can only see their own entries


class APISearchView(generics.ListAPIView):
    """
    Perform a search operaton
    q -- Term that will be used for the search.
    """

    filter_backends = (MayanObjectPermissionsFilter,)

    # Placeholder serializer to avoid errors with Django REST swagger
    serializer_class = SearchSerializer

    def get_queryset(self):
        document_search = SearchModel.get('documents.Document')
        self.serializer_class = document_search.serializer
        self.mayan_object_permissions = {'GET': [document_search.permission]}

        try:
            queryset, ids, timedelta = document_search.search(self.request.GET, self.request.user)
        except Exception as exception:
            raise ParseError(unicode(exception))

        return queryset


class APIGetId(generics.RetrieveAPIView):
    """
    Returns the selected document.
    """

    serializer_class = DocumentIdSerializer
    lookup_field = 'label'
    queryset = Document.objects.all()

    permission_classes = (MayanPermission,)
    mayan_object_permissions = {
        'GET': [PERMISSION_DOCUMENT_VIEW],
    }
