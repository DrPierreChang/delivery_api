from rest_framework.response import Response
from rest_framework.views import APIView

from base.permissions import IsDriver
from custom_auth.permissions import UserIsAuthenticated

from .serializers import MerchantSerializer


class MerchantView(APIView):
    permission_classes = (UserIsAuthenticated, IsDriver)

    def get(self, request, **kwargs):
        return Response(data=MerchantSerializer(request.user.current_merchant).data)
