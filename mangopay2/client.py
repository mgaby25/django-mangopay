from django.conf import settings
from mangopay.auth import StaticStorageStrategy

import mangopay
from mangopay.api import APIRequest


def get_mangopay_api_handler():
    return APIRequest(storage_strategy=StaticStorageStrategy())


mangopay.client_id = settings.MANGOPAY_CLIENT_ID
mangopay.apikey = settings.MANGOPAY_PASSPHRASE
mangopay.sandbox = settings.MANGOPAY_SANDBOX
mangopay.get_default_handler = get_mangopay_api_handler
