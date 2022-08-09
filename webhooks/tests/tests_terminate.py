import mock

from tasks.models.orders import OrderStatus
from tasks.tests.tests_orders_with_terminate_codes import InitializeTestCase


class TerminateOrderWithCorrectCodeTestCase(InitializeTestCase):

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_delivered_by_driver_with_multiple_codes(self, send_external_event):
        terminate_codes = [self.success_codes['STARTING'], self.success_codes['DEFAULT_CODES'][1]['code']]
        self.change_status_to(
            self.driver,
            self.order,
            OrderStatus.DELIVERED,
            terminate_codes=terminate_codes,
            terminate_comment='Test'
        )

        self.assertEqual(self.order.terminate_codes.count(), len(terminate_codes))

        external_data = send_external_event.call_args_list[1][0][1]
        self.assertIsNotNone(external_data)
        self.assertFalse('order_confirmation_documents' in external_data['order_info'])
