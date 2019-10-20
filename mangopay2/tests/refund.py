from django.test import TestCase

from unittest.mock import patch

from ..models import MangoPayInRefund

from .factories import MangoPayInRefundFactory
from .client import MockMangoPayApi


class MangoPayRefundTests(TestCase):

    def setUp(self):
        self.refund = MangoPayInRefundFactory(mangopay_pay_in__mangopay_id=2)

    @patch("mangopay2.models.get_mangopay_api_client")
    def test_create(self, mock_client):
        id = 222
        mock_client.return_value = MockMangoPayApi(refund_id=id)
        self.assertIsNone(self.refund.mangopay_id)
        self.refund.create()
        MangoPayInRefund.objects.get(id=self.refund.id, mangopay_id=id)
