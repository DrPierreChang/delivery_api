from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from constance import config


class MobileAppVersionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, app_type, **kwargs):
        version_config = config.MOBILE_APP_VERSIONS.get(app_type, ['', ''])
        data = dict(zip(['current', 'lowest_allowed'], version_config))
        return Response(data)
