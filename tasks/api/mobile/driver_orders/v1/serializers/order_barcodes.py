from radaro_utils.serializers.mobile.serializers import RadaroMobileModelSerializer
from tasks.models import Order

from ....customers.v1.serializers import CustomerSerializer
from .barcodes import BarcodeSerializer
from .location import OrderLocationSerializer
from .order.main import RODetailsSerializer


class BarcodeMultipleOrdersSerializer(RadaroMobileModelSerializer):
    customer = CustomerSerializer()
    deliver_address = OrderLocationSerializer()
    pickup_address = OrderLocationSerializer()
    barcodes = BarcodeSerializer(many=True)
    ro_details = RODetailsSerializer(source='route_optimisation_details', read_only=True)

    class Meta:
        model = Order
        fields = ('id', 'title', 'customer', 'status', 'deliver_address', 'pickup_address', 'barcodes', 'ro_details')
