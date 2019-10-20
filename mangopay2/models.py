from urllib.request import urlopen
import base64
import jsonfield
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from django.utils.timezone import utc
from mangopay.constants import DOCUMENTS_STATUS_CHOICES, DOCUMENTS_TYPE_CHOICES, LEGAL_USER_TYPE_CHOICES, \
    BANK_ACCOUNT_TYPE_CHOICES, DEPOSIT_CHOICES, STATUS_CHOICES, SECURE_MODE_CHOICES, \
    PAYIN_PAYMENT_TYPE, USER_TYPE_CHOICES
from mangopay.resources import NaturalUser, LegalUser, Document, Page, BankAccount, Wallet, DirectPayIn, Money, \
    BankWirePayIn, BankWirePayOut, Transfer, PayInRefund, CardRegistration
from mangopay.utils import Address
from model_utils.models import TimeStampedModel

from money.contrib.django.models.fields import MoneyField
from model_utils.managers import InheritanceManager
from django_countries.fields import CountryField

from localflavor.generic.models import IBANField, BICField
from money import Money as PythonMoney

import django_filepicker


def python_money_to_mangopay_money(python_money):
    amount = python_money.amount.quantize(Decimal('.01'), rounding=ROUND_FLOOR) * 100
    return Money(amount=int(amount), currency=str(python_money.currency))


def get_execution_date_as_datetime(mangopay_entity):
    execution_date = mangopay_entity.creation_date
    if execution_date:
        formated_date = datetime.fromtimestamp(int(execution_date))
        if settings.USE_TZ:
            return formated_date.replace(tzinfo=utc)
        else:
            return formated_date


class MangoPayUser(TimeStampedModel):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL)
    type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    first_name = models.CharField(null=True, blank=True, max_length=99)
    last_name = models.CharField(null=True, blank=True, max_length=99)
    email = models.EmailField(max_length=254, blank=True, null=True)

    # Light Authentication Field:
    birthday = models.DateField(blank=True, null=True)
    country_of_residence = CountryField()
    nationality = CountryField()

    # Regular Authentication Fields:
    address = models.CharField(blank=True, null=True, max_length=254)

    objects = InheritanceManager()

    def create(self):
        mangopay_user = self.get_user()
        mangopay_user.save()
        self.mangopay_id = mangopay_user.get_pk()
        self.save()

    def update(self):
        mangopay_user = self.get_user()
        mangopay_user.save()

    def is_legal(self):
        return self.type in USER_TYPE_CHOICES.legal

    def is_natural(self):
        return self.type == USER_TYPE_CHOICES.natural

    def has_light_authentication(self):
        raise NotImplemented

    def _required_documents_types(self):
        raise NotImplemented

    def has_regular_authentication(self):
        return (self.has_light_authentication()
                and self._are_required_documents_validated())

    def required_documents_types_that_need_to_be_reuploaded(self):
        return [t for t in self._required_documents_types() if
                self._document_needs_to_be_reuploaded(t)]

    def _document_needs_to_be_reuploaded(self, t):
        return (self.mangopay_documents.filter(
                type=t, status=REFUSED).exists()
                and not self.mangopay_documents.filter(
                    type=t,
                    status__in=[VALIDATED, VALIDATION_ASKED]).exists()
                and not self.mangopay_documents.filter(
                    type=t, status__isnull=True).exists())

    def get_user(self):
        return NotImplementedError

    def _birthday_fmt(self):
        return int(self.birthday.strftime("%s"))

    def _are_required_documents_validated(self):
        are_validated = True
        for type in self._required_documents_types():
            are_validated = self.mangopay_documents.filter(
                type=type, status=VALIDATED).exists() and are_validated
        return are_validated

    @property
    def _first_name(self):
        if self.first_name:
            return self.first_name
        try:
            return self.user.first_name
        except AttributeError:
            pass
        return ''

    @property
    def _last_name(self):
        if self.last_name:
            return self.last_name
        try:
            return self.user.last_name
        except AttributeError:
            pass
        return ''

    @property
    def _email(self):
        if self.email:
            return self.email
        try:
            return self.user.email
        except AttributeError:
            pass
        return ''

    def __str__(self):
        return self._first_name + ' ' + self._last_name


class MangoPayNaturalUser(MangoPayUser):
    # Regular Authentication Fields:
    occupation = models.CharField(max_length=254, blank=True, null=True)
    income_range = models.CharField(max_length=100, blank=True, null=True)

    def get_user(self):
        return NaturalUser(
            id=self.mangopay_id,
            first_name=self._first_name,
            last_name=self._last_name,
            address=Address(address_line_1=self.address),  # TODO: add other address fields
            birthday=self._birthday_fmt(),
            nationality=self.nationality.code,
            country_of_residence=self.country_of_residence.code,
            occupation=self.occupation,
            income_range=self.income_range,
            proof_of_identity=None,
            proof_of_address=None,
            email=self.email,
        )

    def __str__(self):
        return self.user.get_full_name()

    def save(self, *args, **kwargs):
        self.type = USER_TYPE_CHOICES.natural
        return super(MangoPayNaturalUser, self).save(*args, **kwargs)

    def has_light_authentication(self):
        return (self.user
                and self.country_of_residence
                and self.nationality
                and self.birthday)

    def has_regular_authentication(self):
        return (self.address
                and self.occupation
                and self.income_range
                and super(MangoPayNaturalUser, self).has_regular_authentication())

    def _required_documents_types(self):
        return [DOCUMENTS_TYPE_CHOICES.identity_proof]


class MangoPayLegalUser(MangoPayUser):
    legal_person_type = models.CharField(max_length=15, choices=LEGAL_USER_TYPE_CHOICES)
    business_name = models.CharField(max_length=254)
    business_email = models.EmailField(max_length=254)

    # Regular Authentication Fields:
    headquarters_address = models.CharField(max_length=254, blank=True, null=True)

    def get_user(self):
        return LegalUser(
            id=self.mangopay_id,
            email=self.business_email,
            name=self.business_name,
            legal_person_type=self.legal_person_type,
            headquarters_address=Address(address_line_1=self.headquarters_address),
            legal_representative_first_name=self.first_name,
            legal_representative_last_name=self.last_name,
            legal_representative_address=Address(address_line_1=self.address),
            legal_representative_email=self.email,
            legal_representative_birthday=self._birthday_fmt(),
            legal_representative_nationality=self.nationality.code,
            legal_representative_country_of_residence=self.country_of_residence.code,
        )

    def __str__(self):
        return self.business_name if self.business_name else str(self)

    def has_light_authentication(self):
        return (self.type
                and self.business_name
                and self.business_email
                and self.first_name
                and self.last_name
                and self.country_of_residence
                and self.nationality
                and self.birthday)

    def has_regular_authentication(self):
        return (self.address
                and self.headquarters_address
                and self.address
                and self.email
                and super(MangoPayLegalUser, self).has_regular_authentication())

    def _required_documents_types(self):
        types = [DOCUMENTS_TYPE_CHOICES.identity_proof, DOCUMENTS_TYPE_CHOICES.registration_proof]
        if self.legal_person_type == LEGAL_USER_TYPE_CHOICES.business:
            types.append(DOCUMENTS_TYPE_CHOICES.shareholder_declaration)
        elif self.type == LEGAL_USER_TYPE_CHOICES.organization:
            types.append(DOCUMENTS_TYPE_CHOICES.articles_of_association)
        return types


class MangoPayDocument(models.Model):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    mangopay_user = models.ForeignKey(MangoPayUser, related_name="mangopay_documents")
    type = models.CharField(max_length=2, choices=DOCUMENTS_TYPE_CHOICES)
    status = models.CharField(blank=True, null=True, max_length=1, choices=DOCUMENTS_STATUS_CHOICES)
    refused_reason_message = models.CharField(null=True, blank=True, max_length=255)
    refused_reason_type = models.CharField(null=True, blank=True, max_length=255)

    def get_document(self):
        user = self.mangopay_user.get_mango_user()
        return Document(id=self.mangopay_id, user=user, type=self.type)

    def create(self):
        document = self.get_document()
        document.save()
        self.mangopay_id = document.get_pk()
        self.status = document.status
        self.save()

    def get(self):
        document = self.get_document()
        self.refused_reason_type = document.refused_reason_type
        self.refused_reason_message = document.refused_reason_message
        self.status = document.status
        self.save()
        return self

    def ask_for_validation(self):
        if self.status == CREATED:
            document = self.get_document()
            document.status = DOCUMENTS_STATUS_CHOICES.validation_asked
            document.save()
            self.status = document.status
            self.save()
        else:
            raise BaseException('Cannot ask for validation of a document not in the created state')

    def __str__(self):
        return str(self.mangopay_id) + " " + str(self.status)


# TODO: This needs to be reviewed

def page_storage():
    if settings.MANGOPAY_PAGE_DEFAULT_STORAGE:
        return default_storage
    else:
        from storages.backends.s3boto import S3BotoStorage
        return S3BotoStorage(
            acl='private',
            headers={'Content-Disposition': 'attachment',
                     'X-Robots-Tag': 'noindex, nofollow, noimageindex'},
            bucket=settings.AWS_MEDIA_BUCKET_NAME,
            custom_domain=settings.AWS_MEDIA_CUSTOM_DOMAIN)


class MangoPayPage(models.Model):
    document = models.ForeignKey(MangoPayDocument, related_name="mangopay_pages")
    file = django_filepicker.models.FPUrlField(
        max_length=255,
        additional_params={
            'data-fp-store-path': 'mangopay_pages/',
            'data-fp-store-location': 'S3',
        })

    def create(self):
        document = self.document.get_document()
        user = self.document.mangopay_user.get_user()
        encoded_file = self._file_bytes().decode("utf-8")
        page = Page(document=document, file=encoded_file, user=user)
        page.save()

    def _file_bytes(self):
        response = urlopen(self.file)
        bytes = base64.b64encode(response.read())
        return bytes


class MangoPayBankAccount(models.Model):
    mangopay_user = models.ForeignKey(MangoPayUser, related_name="mangopay_bank_accounts")
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)

    address = models.CharField(max_length=254)
    account_type = models.CharField(
        max_length=2, choices=BANK_ACCOUNT_TYPE_CHOICES, default=BANK_ACCOUNT_TYPE_CHOICES.iban
    )
    iban = IBANField(blank=True, null=True)

    bic = BICField(blank=True, null=True)
    country = CountryField(null=True, blank=True)
    account_number = models.CharField(max_length=15, null=True, blank=True)

    # BA_US type only fields
    aba = models.CharField(max_length=9, null=True, blank=True)
    deposit_account_type = models.CharField(max_length=8, choices=DEPOSIT_CHOICES, default=DEPOSIT_CHOICES.checking)

    def get_bank_account(self):
        bank_account = BankAccount(
            id=self.mangopay_id,
            owner_name=self.mangopay_user.user.get_full_name(),
            owner_address=Address(address_line_1=self.address),
            user=self.mangopay_user.get_user(),
            type=self.account_type
        )

        if self.account_type == BANK_ACCOUNT_TYPE_CHOICES.iban:
            bank_account.iban = self.iban
        elif self.account_type == BANK_ACCOUNT_TYPE_CHOICES.us:
            bank_account.aba = self.aba
            bank_account.deposit_account_type = self.deposit_account_type
            bank_account.account_number = self.account_number
        elif self.account_type == BANK_ACCOUNT_TYPE_CHOICES.other:
            bank_account.account_number = self.account_number
        else:
            raise NotImplementedError("Bank Account Type ({0}) not implemented.".format(self.account_type))

        return bank_account

    def create(self):
        bank_account = self.get_bank_account()
        bank_account.save()
        self.mangopay_id = bank_account.get_pk()
        self.save()


class MangoPayWallet(models.Model):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    mangopay_user = models.ForeignKey(MangoPayUser, related_name="mangopay_wallets")
    currency = models.CharField(max_length=3, default="EUR")
    description = models.CharField(max_length=255, blank=True, null=True)

    def get_wallet(self):
        user = self.mangopay_user.get_user()
        return Wallet(id=self.mangopay_id, owners=[user], description=self.description, currency=self.currency)

    def create(self):
        wallet = self.get_wallet()
        wallet.save()
        self.mangopay_id = wallet.get_pk()
        self.save()

    def balance(self):
        wallet = self.get_wallet()
        if not wallet.balance:
            return

        return PythonMoney(wallet.balance.amount / 100.0, wallet.balance.currency)


class MangoPayPayIn(models.Model):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    mangopay_user = models.ForeignKey(MangoPayUser, related_name="mangopay_payins")
    mangopay_wallet = models.ForeignKey(MangoPayWallet, related_name="mangopay_payins")

    execution_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=9, choices=STATUS_CHOICES, blank=True, null=True)
    debited_funds = MoneyField(default=0, default_currency="EUR", decimal_places=2, max_digits=12)
    fees = MoneyField(default=0, default_currency="EUR", decimal_places=2, max_digits=12)
    result_code = models.CharField(null=True, blank=True, max_length=6)
    payment_type = models.CharField(null=False, blank=False, choices=PAYIN_PAYMENT_TYPE, max_length=10)

    # Pay in by card via web - mangopay_card needs custom validation so it's not null on save
    mangopay_card = models.ForeignKey("MangoPayCard", related_name="mangopay_payins", null=True, blank=True)
    secure_mode_redirect_url = models.URLField(null=True, blank=True)

    # Pay in via bank wire
    wire_reference = models.CharField(null=True, blank=True, max_length=50)
    mangopay_bank_account = jsonfield.JSONField(null=True, blank=True)

    def create(self):
        pay_in = self.get_pay_in()
        self.mangopay_id = pay_in.get_pk()
        self._update(pay_in)

    def get_pay_in(self):
        raise NotImplemented

    def _update(self, pay_in):
        self.execution_date = get_execution_date_as_datetime(pay_in)
        self.status = pay_in.status
        self.save()
        return self


class MangoPayDirectPayIn(MangoPayPayIn):

    class Meta:
        proxy = True

    def get_pay_in(self):
        author = self.mangopay_user.get_user()
        credited_wallet = self.mangopay_wallet.get_wallet()
        card = '' # TODO: Add Card
        return DirectPayIn(
            author=author,
            debited_funds=python_money_to_mangopay_money(self.debited_funds),
            fees=python_money_to_mangopay_money(self.fees),
            credited_wallet=credited_wallet,
            secure_mode_return_url=self.secure_mode_return_url,
            secure_mode=SECURE_MODE_CHOICES.default,
            payment_type=PAYIN_PAYMENT_TYPE.card
        )


class MangoPayPayInBankWire(MangoPayPayIn):

    class Meta:
        proxy = True

    def get_pay_in(self):
        author = self.mangopay_user.get_user()
        credited_wallet = self.mangopay_wallet.get_wallet()
        return BankWirePayIn(
            author=author,
            declared_debited_funds=python_money_to_mangopay_money(self.debited_funds),
            declared_fees=python_money_to_mangopay_money(self.fees),
            credited_wallet=credited_wallet,
            payment_type=PAYIN_PAYMENT_TYPE.bank_wire
        )

    def _update(self, pay_in):
        self.wire_reference = pay_in.wire_reference
        return super()._update(pay_in)


class MangoPayPayOut(models.Model):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    mangopay_user = models.ForeignKey(MangoPayUser, related_name="mangopay_payouts")
    mangopay_wallet = models.ForeignKey(MangoPayWallet, related_name="mangopay_payouts")
    mangopay_bank_account = models.ForeignKey(MangoPayBankAccount, related_name="mangopay_payouts")
    execution_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=9, choices=STATUS_CHOICES, blank=True, null=True)
    debited_funds = MoneyField(default=0, default_currency="EUR", decimal_places=2, max_digits=12)
    fees = MoneyField(default=0, default_currency="EUR", decimal_places=2, max_digits=12)

    def get_pay_out(self):
        author = self.mangopay_user.get_user()
        bank_account = self.mangopay_bank_account.get_bank_account()
        return BankWirePayOut(
            id=self.mangopay_id,
            author=author,
            debited_funds=python_money_to_mangopay_money(self.debited_funds),
            fees=python_money_to_mangopay_money(self.fees),
            debited_wallet=self.mangopay_wallet,
            bank_account=bank_account,
            bank_wire_ref="John Doe's trousers"
        )

    def create(self):
        payout = self.get_pay_out()
        payout.save()
        self.mangopay_id = payout.get_pk()
        return self._update(payout)

    def _update(self, pay_out):
        self.execution_date = get_execution_date_as_datetime(pay_out)
        self.status = pay_out.status
        self.save()
        return self



# TODO: This needs more investigations


class MangoPayCard(models.Model):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    expiration_date = models.CharField(blank=True, null=True, max_length=4)
    alias = models.CharField(blank=True, null=True, max_length=16)
    is_active = models.BooleanField(default=False)
    is_valid = models.NullBooleanField()

    def request_card_info(self):
        if self.mangopay_id:
            client = get_mangopay_api_client()
            card = client.cards.Get(self.mangopay_id)
            self.expiration_date = card.ExpirationDate
            self.alias = card.Alias
            self.is_active = card.Active
            if card.Validity == "UNKNOWN":
                self.is_valid = None
            else:
                self.is_valid = card.Validity == "VALID"


class MangoPayCardRegistration(models.Model):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    mangopay_user = models.ForeignKey(MangoPayUser, related_name="mangopay_card_registrations")
    mangopay_card = models.OneToOneField(
        MangoPayCard, null=True, blank=True, related_name="mangopay_card_registration"
    )

    def get_card_registration(self, currency='EUR'):
        user = self.mangopay_user.get_user()
        return CardRegistration(id=self.mangopay_id, user=user, currency=currency)

    def create(self):
        card_registration = self.get_card_registration()
        card_registration.save()
        self.mangopay_id = card_registration.get_pk()
        self.save()

    def get_preregistration_data(self):
        card_registration = self.get_card_registration()
        preregistration_data = {
            "preregistrationData": card_registration.preregistration_data,
            "accessKey": card_registration.access_key,
            "cardRegistrationURL": card_registration.card_registration_url
        }
        return preregistration_data

    def save_mangopay_card_id(self, mangopay_card_id):
        self.mangopay_card.mangopay_id = mangopay_card_id
        self.mangopay_card.save()

    def save(self, *args, **kwargs):
        if not self.mangopay_card:
            mangopay_card = MangoPayCard()
            mangopay_card.save()
            self.mangopay_card = mangopay_card
        super(MangoPayCardRegistration, self).save(*args, **kwargs)


class MangoPayInRefund(models.Model):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    mangopay_user = models.ForeignKey(MangoPayUser, related_name="mangopay_refunds")
    mangopay_pay_in = models.ForeignKey(MangoPayPayIn, related_name="mangopay_refunds")
    execution_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=9, choices=STATUS_CHOICES, blank=True, null=True)
    result_code = models.CharField(null=True, blank=True, max_length=6)

    def create(self):
        author = self.mangopay_user.get_user()
        payin = self.mangopay_pay_in.get_pay_in()
        payin_refund = PayInRefund(
            author=author,
            payin=payin,
        )
        payin_refund.save()
        self.mangopay_id = payin_refund.get_pk()
        self.status = payin_refund.status
        self.result_code = payin_refund.result_code
        self.execution_date = get_execution_date_as_datetime(payin_refund)
        self.save()
        return self


class MangoPayTransfer(models.Model):
    mangopay_id = models.PositiveIntegerField(null=True, blank=True)
    mangopay_debited_wallet = models.ForeignKey(MangoPayWallet, related_name="mangopay_debited_wallets")
    mangopay_credited_wallet = models.ForeignKey(MangoPayWallet, related_name="mangopay_credited_wallets")
    debited_funds = MoneyField(default=0, default_currency="EUR", decimal_places=2, max_digits=12)
    fees = MoneyField(default=0, default_currency="EUR", decimal_places=2, max_digits=12)
    execution_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=9, choices=STATUS_CHOICES, blank=True, null=True)
    result_code = models.CharField(null=True, blank=True, max_length=6)

    def get_transfer(self):
        author = self.mangopay_debited_wallet.mangopay_user.get_user()
        debited_wallet = self.mangopay_debited_wallet.get_wallet()

        credited_user = self.mangopay_credited_wallet.mangopay_user.get_user()
        credited_wallet = self.mangopay_credited_wallet.get_wallet()

        return Transfer(
            id=self.mangopay_id,
            author=author,
            credited_user=credited_user,
            debited_funds=python_money_to_mangopay_money(self.debited_funds),
            fees=python_money_to_mangopay_money(self.fees),
            debited_wallet=debited_wallet,
            credited_wallet=credited_wallet
        )

    def create(self):
        transfer = self.get_transfer()
        transfer.save()
        self.mangopay_id = transfer.get_pk()
        self._update(transfer)

    def _update(self, transfer):
        self.status = transfer.status
        self.result_code = transfer.result_code
        self.execution_date = get_execution_date_as_datetime(transfer)
        self.save()
