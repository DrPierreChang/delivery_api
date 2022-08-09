from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import ManagerFactory
from merchant.factories import LabelFactory, MerchantFactory
from merchant.models import Label, label


class MerchantLabelsTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(MerchantLabelsTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(enable_labels=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def setUp(self):
        self.label = LabelFactory(merchant=self.merchant, color=Label.DARK_RED, name="Test")
        self.another_label = LabelFactory(merchant=self.merchant, color=Label.BURGUNDY, name="Test")
        self.client.force_authenticate(self.manager)

    def test_merchant_colors(self):
        for setting in ({
            'params': '',
            'colors': Label.BASE_COLORS,
        }, {
            'params': '?full_color_map=true',
            'colors': label.COLORS_MAP
        }):
            resp = self.client.get('/api/users/me/' + setting['params'])
            label_colors = resp.data['merchant']['labels_colors']
            self.assertDictEqual(label_colors, setting['colors'])
            resp = self.client.get('/api/merchant/my/labels/colors/' + setting['params'])
            self.assertDictEqual(label_colors, resp.data)

    def _test_create_label(self, version=1):
        url = '/api/v2/merchant/my/labels/' if version == 2 else '/api/merchant/my/labels/'
        bad_data = {
            "name": "Test",
            "color": Label.BASE_COLORS[Label.BURGUNDY] if version == 2 else Label.BURGUNDY
        }
        resp = self.client.post(url, data=bad_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        data = {
            "name": "Active",
            "color": Label.BASE_COLORS[Label.YELLOW] if version == 2 else Label.YELLOW
        }

        resp = self.client.post(url, data=data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        resp_json_data = resp.json()
        self.assertTrue(Label.objects.filter(id=resp_json_data['id'], merchant_id=self.merchant.id).exists())

    def _test_create_label_without_color(self, version=1):
        url = '/api/v2/merchant/my/labels/' if version == 2 else '/api/merchant/my/labels/'
        data = {
            "name": "Empty label"
        }

        resp = self.client.post(url, data=data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        resp_json_data = resp.json()
        label_qs = Label.objects.filter(id=resp_json_data['id'], merchant_id=self.merchant.id)
        self.assertTrue(label_qs.exists())
        self.assertEqual(label_qs.first().color, Label.NO_COLOR)

    def test_create_label(self):
        self._test_create_label()

    def test_create_label_v2(self):
        self._test_create_label(version=2)

    def test_create_label_without_color(self):
        self._test_create_label_without_color()

    def test_create_label_without_color_v2(self):
        self._test_create_label_without_color(version=2)

    def test_create_multiple_labels(self):
        labels = LabelFactory.create_batch(50, merchant=self.merchant)
        data = {
            "name": "Dark green label",
            "color": Label.DARK_GREEN
        }

        resp = self.client.post('/api/merchant/my/labels/', data=data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_labels_list(self):
        LabelFactory(color="green", merchant=self.merchant)
        resp = self.client.get('/api/merchant/my/labels/')
        resp_json_data = resp.json()
        self.assertGreater(resp_json_data.get('count'), 0)

    def test_get_label(self):
        resp = self.client.get('/api/merchant/my/labels/{}'.format(self.label.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        json_data = resp.json()
        self.assertEqual(json_data['id'], self.label.id)

    def test_label_color_v2(self):
        resp = self.client.get('/api/v2/merchant/my/labels/{}'.format(self.label.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        json_data = resp.json()
        self.assertEqual(json_data['color'], Label.BASE_COLORS[self.label.color])

    def _test_label_update(self, version=1):
        url = '/api/v2/merchant/my/labels/{}' if version == 2 else '/api/merchant/my/labels/{}'
        resp = self.client.patch(
            url.format(self.label.id),
            data={"color": Label.BASE_COLORS[Label.DARK_RED] if version == 2 else Label.DARK_RED,
                  "name": "Test"}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.patch(
            url.format(self.label.id),
            data={"color": Label.BASE_COLORS[Label.BURGUNDY] if version == 2 else Label.BURGUNDY,
                  "name": "Test"}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.patch(url.format(self.label.id),
                                 data={"color": "black" if version >= 2 else "#000000"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.patch(
            url.format(self.label.id),
            data={"color": Label.BASE_COLORS[Label.DARK_GREEN] if version == 2 else Label.DARK_GREEN}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        label = Label.objects.get(id=self.label.id)
        self.assertEqual(label.color, Label.DARK_GREEN)

    def test_label_update(self):
        self._test_label_update()

    def test_label_update_v2(self):
        self._test_label_update(version=2)

    def test_label_delete(self):
        label_id = self.label.id
        resp = self.client.delete('/api/merchant/my/labels/{}'.format(self.label.id))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

        self.assertFalse(Label.objects.filter(id=label_id, merchant_id=self.merchant.id).exists())

    def test_get_available_colors(self):
        resp = self.client.get('/api/merchant/my/labels/available-colors')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.json()
        colors = data.get('available_colors')

        self.assertEqual(len(colors), len(Label.color_choices)-2)
        self.assertTrue(self.label.color not in colors)
