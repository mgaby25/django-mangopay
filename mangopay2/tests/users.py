from django.test import TestCase

from unittest.mock import patch

from mangopay.constants import DOCUMENTS_TYPE_CHOICES, DOCUMENTS_STATUS_CHOICES, USER_TYPE_CHOICES, \
    LEGAL_USER_TYPE_CHOICES

from ..models import MangoPayNaturalUser, MangoPayLegalUser

from .factories import (
    LightAuthenticationMangoPayNaturalUserFactory, RegularAuthenticationMangoPayNaturalUserFactory,
    LightAuthenticationMangoPayLegalUserFactory, RegularAuthenticationMangoPayLegalUserFactory,
    MangoPayDocumentFactory
)
from .client import MockMangoPayApi

IDENTITY_PROOF = DOCUMENTS_TYPE_CHOICES.identity_proof
REGISTRATION_PROOF = DOCUMENTS_TYPE_CHOICES.registration_proof
SHAREHOLDER_DECLARATION = DOCUMENTS_TYPE_CHOICES.shareholder_declaration
ARTICLES_OF_ASSOCIATION = DOCUMENTS_TYPE_CHOICES.articles_of_association

VALIDATED = DOCUMENTS_STATUS_CHOICES.validated


class AbstractMangoPayUserTests(object):

    @patch("mangopay2.client.get_mangopay_api_handler")
    def test_user_created(self, mock_client):
        id = 22
        mock_client.return_value = MockMangoPayApi(user_id=id)
        self.assertIsNone(self.user.mangopay_id)
        self.user.create()
        self.klass.objects.get(id=self.user.id, mangopay_id=id)

    @patch("mangopay2.client.get_mangopay_api_handler")
    def test_user_updated(self, mock_client):
        mock_client.return_value = MockMangoPayApi(user_id=id)
        self.user.mangopay_id = 33
        self.user.update()


class AbstractMangoPayNaturalUserTests(AbstractMangoPayUserTests):

    def setUp(self):
        self.klass = MangoPayNaturalUser

    def test_save_saves_type(self):
        self.assertEqual(self.user.type, USER_TYPE_CHOICES.natural)
        self.assertFalse(self.user.is_legal())
        self.assertTrue(self.user.is_natural())


class LightAuthenticationMangoPayNaturalUserTests(
        AbstractMangoPayNaturalUserTests, TestCase):

    def setUp(self):
        super(LightAuthenticationMangoPayNaturalUserTests, self).setUp()
        self.user = LightAuthenticationMangoPayNaturalUserFactory()

    def test_has_authentication_levels(self):
        self.assertTrue(self.user.has_light_authentication())
        self.assertFalse(self.user.has_regular_authentication())


class RegularAuthenticationMangoPayNaturalUserTests(
        AbstractMangoPayNaturalUserTests, TestCase):

    def setUp(self):
        super(RegularAuthenticationMangoPayNaturalUserTests, self).setUp()
        self.user = RegularAuthenticationMangoPayNaturalUserFactory()
        self.document = MangoPayDocumentFactory(mangopay_user=self.user,
                                                type=IDENTITY_PROOF,
                                                status=VALIDATED)

    def test_has_authentication_levels(self):
        self.assertTrue(self.user.has_light_authentication())
        self.assertTrue(self.user.has_regular_authentication())

    def test_required_documents_types_that_need_to_be_reuploaded(self):
        self.assertEqual(
            self.user.required_documents_types_that_need_to_be_reuploaded(),
            [])
        self.document.status = REFUSED
        self.document.save()
        self.assertEqual(
            self.user.required_documents_types_that_need_to_be_reuploaded(),
            [IDENTITY_PROOF])
        MangoPayDocumentFactory(mangopay_user=self.user, type=IDENTITY_PROOF,
                                status=None)
        self.assertEqual(
            self.user.required_documents_types_that_need_to_be_reuploaded(),
            [])


class AbstractMangoPayLegalUserTests(AbstractMangoPayUserTests):

    def setUp(self):
        self.klass = MangoPayLegalUser

    def test_save_saves_type(self):
        self.assertEqual(self.user.legal_person_type, LEGAL_USER_TYPE_CHOICES.business)
        self.assertTrue(self.user.is_legal())
        self.assertFalse(self.user.is_natural())


class LightAuthenticationMangoPayLegalUserTests(
        AbstractMangoPayLegalUserTests, TestCase):

    def setUp(self):
        super(LightAuthenticationMangoPayLegalUserTests, self).setUp()
        self.user = LightAuthenticationMangoPayLegalUserFactory()

    def test_has_authentication_levels(self):
        self.assertTrue(self.user.has_light_authentication())
        self.assertFalse(self.user.has_regular_authentication())


class RegularAuthenticationMangoPayLegalUserTests(
        AbstractMangoPayLegalUserTests, TestCase):

    def setUp(self):
        super(RegularAuthenticationMangoPayLegalUserTests, self).setUp()
        self.user = RegularAuthenticationMangoPayLegalUserFactory()
        self.identity_proof = MangoPayDocumentFactory(
            mangopay_user=self.user, type=IDENTITY_PROOF,
            status=VALIDATED)
        self.registration_proof = MangoPayDocumentFactory(
            mangopay_user=self.user, type=REGISTRATION_PROOF,
            status=VALIDATED)
        self.shareholder_declaration = MangoPayDocumentFactory(
            mangopay_user=self.user, type=SHAREHOLDER_DECLARATION,
            status=VALIDATED)
        self.articles_of_association = MangoPayDocumentFactory(
            mangopay_user=self.user, type=ARTICLES_OF_ASSOCIATION,
            status=VALIDATED)

    def test_has_authentication_levels(self):
        self.assertTrue(self.user.has_light_authentication())
        self.assertTrue(self.user.has_regular_authentication())

    def test_required_documents_types_that_need_to_be_reuploaded(self):
        self.assertEqual(
            self.user.required_documents_types_that_need_to_be_reuploaded(),
            [])
        self.identity_proof.status = REFUSED
        self.identity_proof.save()
        self.registration_proof.status = REFUSED
        self.registration_proof.save()
        self.shareholder_declaration.status = REFUSED
        self.shareholder_declaration.save()
        self.assertEqual(
            self.user.required_documents_types_that_need_to_be_reuploaded(),
            [IDENTITY_PROOF, REGISTRATION_PROOF, SHAREHOLDER_DECLARATION])
        MangoPayDocumentFactory(mangopay_user=self.user,
                                type=IDENTITY_PROOF,
                                status=VALIDATION_ASKED)
        self.assertEqual(
            self.user.required_documents_types_that_need_to_be_reuploaded(),
            [REGISTRATION_PROOF, SHAREHOLDER_DECLARATION])
        MangoPayDocumentFactory(mangopay_user=self.user,
                                type=SHAREHOLDER_DECLARATION,
                                status=VALIDATION_ASKED)
        self.assertEqual(
            self.user.required_documents_types_that_need_to_be_reuploaded(),
            [REGISTRATION_PROOF])
        MangoPayDocumentFactory(mangopay_user=self.user,
                                type=REGISTRATION_PROOF,
                                status=VALIDATED)
        self.assertEqual(
            self.user.required_documents_types_that_need_to_be_reuploaded(),
            [])
