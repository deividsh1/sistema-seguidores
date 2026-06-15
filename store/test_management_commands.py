import hashlib
import hmac
import json
import time
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from store.models import Order, OrderItem, Package, PaymentLog, Platform, ProviderLog, Service
from store.services.payment_api import PaymentWebhookValidationError


@override_settings(
    PAYMENT_SIMULATED=False,
    PAYMENT_PROVIDER="mercadopago",
    PROVIDER_SIMULATED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class MercadoPagoManagementCommandTests(TestCase):
    def setUp(self):
        platform = Platform.objects.create(name="Instagram", slug="instagram")
        service = Service.objects.create(
            platform=platform,
            name="Seguidores",
            slug="seguidores",
            provider_service_id="9142",
        )
        package = Package.objects.create(
            service=service,
            name="500",
            quantity=500,
            price_brl=Decimal("29.90"),
        )
        self.order = Order.objects.create(
            package=package,
            platform_name=platform.name,
            service_name=service.name,
            package_name=package.name,
            provider_service_id=service.provider_service_id,
            target="@cliente",
            quantity=package.quantity,
            amount_brl=package.price_brl,
            whatsapp="11999999999",
            email="cliente@example.com",
            external_payment_id="pay-123",
        )
        OrderItem.objects.create(
            order=self.order,
            package=package,
            service_name=service.name,
            package_name=package.name,
            provider_service_id=service.provider_service_id,
            target=self.order.target,
            quantity=package.quantity,
            total_amount=package.price_brl,
        )
        self.charge = PaymentLog.objects.create(
            order=self.order,
            event_type=PaymentLog.EventType.CHARGE,
            external_payment_id=self.order.external_payment_id,
            status="pending",
            amount=self.order.amount_brl,
            payment_url="https://payments.example/pix",
        )

    def payment(self, status="pending", external_reference=None):
        return {
            "id": self.order.external_payment_id,
            "external_payment_id": self.order.external_payment_id,
            "external_reference": external_reference or self.order.code,
            "status": status,
            "amount": self.order.amount_brl,
            "raw": {"id": self.order.external_payment_id, "status": status},
        }

    @patch("store.management.commands.mp_status.get_payment_status")
    def test_mp_status_reports_without_altering_database(self, get_status):
        get_status.return_value = self.payment()
        output = StringIO()
        log_count = PaymentLog.objects.count()

        call_command("mp_status", self.order.code.lower(), stdout=output)

        result = output.getvalue()
        self.assertIn(f"Código do pedido: {self.order.code}", result)
        self.assertIn("Status do pedido: pending", result)
        self.assertIn("Payment ID externo: pay-123", result)
        self.assertIn("PaymentLog mais recente: charge / pending", result)
        self.assertIn("Payment URL: https://payments.example/pix", result)
        self.assertIn("Status Mercado Pago: pending", result)
        self.assertIn(f"External reference Mercado Pago: {self.order.code}", result)
        self.assertIn("Valor Mercado Pago: 29.90", result)
        self.assertEqual(PaymentLog.objects.count(), log_count)
        get_status.assert_called_once_with("pay-123")

    @patch("store.management.commands.mp_sync.get_payment_status")
    def test_mp_sync_pending_does_not_alter_database(self, get_status):
        get_status.return_value = self.payment()
        output = StringIO()
        log_count = PaymentLog.objects.count()

        call_command("mp_sync", self.order.code, stdout=output)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(PaymentLog.objects.count(), log_count)
        self.assertIn("continua pendente", output.getvalue())

    @patch("store.management.commands.mp_sync.get_payment_status")
    def test_mp_sync_terminal_statuses_do_not_mark_paid(self, get_status):
        log_count = PaymentLog.objects.count()

        for status in ("rejected", "cancelled", "expired"):
            with self.subTest(status=status):
                get_status.return_value = self.payment(status=status)
                output = StringIO()
                call_command("mp_sync", self.order.code, stdout=output)
                self.assertIn("não foi marcado como pago", output.getvalue())

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(PaymentLog.objects.count(), log_count)

    @patch("store.management.commands.mp_sync.get_payment_status")
    def test_mp_sync_aborts_on_external_reference_mismatch(self, get_status):
        get_status.return_value = self.payment(external_reference="OUTRO-PEDIDO")

        with self.assertRaisesMessage(CommandError, "External reference"):
            call_command("mp_sync", self.order.code)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(PaymentLog.objects.count(), 1)

    @patch("store.services.provider_api.provider_request")
    @patch("store.management.commands.mp_sync.get_payment_status")
    def test_mp_sync_approved_uses_existing_processor_and_simulated_provider(
        self, get_status, provider_request
    ):
        get_status.return_value = self.payment(status="approved")
        output = StringIO()

        call_command("mp_sync", self.order.code, stdout=output)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(
            self.order.fulfillment_status, Order.FulfillmentStatus.SUBMITTED
        )
        self.assertTrue(
            self.order.payment_logs.filter(
                event_type=PaymentLog.EventType.STATUS,
                status="approved",
            ).exists()
        )
        self.assertTrue(
            ProviderLog.objects.filter(
                order=self.order,
                action="submit_simulated",
            ).exists()
        )
        provider_request.assert_not_called()
        self.assertIn("Provedor: simulado", output.getvalue())

    def test_commands_reject_unknown_order(self):
        for command in ("mp_status", "mp_sync"):
            with self.subTest(command=command):
                with self.assertRaisesMessage(CommandError, "não encontrado"):
                    call_command(command, "CODIGO-INEXISTENTE")


class MercadoPagoWebhookLoggingTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("store.views.process_payment_notification", return_value=True)
    @patch("store.views.parse_payment_webhook")
    def test_accepted_webhook_log_contains_only_payment_id_and_type(
        self, parse_webhook, process_notification
    ):
        parse_webhook.return_value = {
            "external_payment_id": "pay-123",
            "event_type": "webhook",
        }

        with self.assertLogs("store.views", level="INFO") as logs:
            response = self.client.post(
                reverse("store:mercadopago_webhook"),
                data="{}",
                content_type="application/json",
                HTTP_X_SIGNATURE="assinatura-que-nao-deve-ser-logada",
            )

        self.assertEqual(response.status_code, 200)
        joined = " ".join(logs.output)
        self.assertIn("payment_id=pay-123", joined)
        self.assertIn("type=payment", joined)
        self.assertNotIn("assinatura-que-nao-deve-ser-logada", joined)
        process_notification.assert_called_once()

    @patch(
        "store.views.parse_payment_webhook",
        side_effect=PaymentWebhookValidationError("motivo técnico sensível"),
    )
    def test_rejected_webhook_log_remains_generic(self, parse_webhook):
        with self.assertLogs("store.views", level="WARNING") as logs:
            response = self.client.post(
                reverse("store:mercadopago_webhook"),
                data="{}",
                content_type="application/json",
                HTTP_X_SIGNATURE="assinatura-que-nao-deve-ser-logada",
            )

        self.assertEqual(response.status_code, 401)
        joined = " ".join(logs.output)
        self.assertIn("rejeitado por validação", joined)
        self.assertNotIn("motivo técnico sensível", joined)
        self.assertNotIn("assinatura-que-nao-deve-ser-logada", joined)


@override_settings(
    PAYMENT_SIMULATED=False,
    PAYMENT_PROVIDER="mercadopago",
    MERCADO_PAGO_WEBHOOK_SECRET="mercado-pago-webhook-secret-long",
)
class MercadoPagoLegacyNotificationTests(TestCase):
    def setUp(self):
        cache.clear()
        platform = Platform.objects.create(name="Instagram", slug="instagram")
        service = Service.objects.create(
            platform=platform,
            name="Seguidores",
            slug="seguidores",
            provider_service_id="9142",
        )
        package = Package.objects.create(
            service=service,
            name="500",
            quantity=500,
            price_brl=Decimal("29.90"),
        )
        self.order = Order.objects.create(
            package=package,
            platform_name=platform.name,
            service_name=service.name,
            package_name=package.name,
            provider_service_id=service.provider_service_id,
            target="@cliente",
            quantity=package.quantity,
            amount_brl=package.price_brl,
            whatsapp="11999999999",
            email="cliente@example.com",
            external_payment_id="pay-legacy-123",
        )
        self.charge = PaymentLog.objects.create(
            order=self.order,
            event_type=PaymentLog.EventType.CHARGE,
            external_payment_id=self.order.external_payment_id,
            status="pending",
            amount=self.order.amount_brl,
        )

    def legacy_url(self, topic="payment"):
        return (
            f"{reverse('store:mercadopago_webhook')}"
            f"?id={self.order.external_payment_id}&topic={topic}"
        )

    @patch("store.services.payment_api.get_payment_status")
    def test_unprocessed_legacy_notification_remains_unauthorized(self, get_status):
        response = self.client.post(
            self.legacy_url(),
            data="{}",
            content_type="application/json",
            HTTP_X_SIGNATURE="assinatura-legada-nao-validavel",
            HTTP_X_REQUEST_ID="request-legacy",
        )

        self.assertEqual(response.status_code, 401)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(self.order.payment_logs.count(), 1)
        get_status.assert_not_called()

    @patch("store.services.payment_api.get_payment_status")
    def test_processed_legacy_duplicate_returns_200_without_reprocessing(
        self, get_status
    ):
        self.order.mark_paid()
        self.order.save(update_fields=("payment_status", "paid_at", "updated_at"))
        PaymentLog.objects.create(
            order=self.order,
            event_type=PaymentLog.EventType.WEBHOOK,
            external_payment_id=self.order.external_payment_id,
            status="approved",
            amount=self.order.amount_brl,
            signature_valid=True,
        )
        log_count = self.order.payment_logs.count()

        with self.assertLogs("store.views", level="INFO") as logs:
            response = self.client.post(
                self.legacy_url(),
                data="{}",
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.order.payment_logs.count(), log_count)
        self.assertIn("IPN legada duplicada ignorada", " ".join(logs.output))
        get_status.assert_not_called()

    def test_legacy_non_payment_topic_remains_unauthorized(self):
        response = self.client.post(
            self.legacy_url(topic="merchant_order"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    @patch("store.views.process_payment_notification", return_value=True)
    @patch("store.services.payment_api.get_payment_status")
    def test_modern_notification_with_top_level_id_is_not_treated_as_legacy(
        self, get_status, process_notification
    ):
        request_id = "request-modern"
        timestamp = str(int(time.time()))
        manifest = (
            f"id:{self.order.external_payment_id};"
            f"request-id:{request_id};ts:{timestamp};"
        )
        signature = hmac.new(
            b"mercado-pago-webhook-secret-long",
            manifest.encode(),
            hashlib.sha256,
        ).hexdigest()
        get_status.return_value = {
            "id": self.order.external_payment_id,
            "external_payment_id": self.order.external_payment_id,
            "external_reference": self.order.code,
            "status": "approved",
            "amount": self.order.amount_brl,
            "raw": {},
        }

        response = self.client.post(
            (
                f"{reverse('store:mercadopago_webhook')}"
                f"?data.id={self.order.external_payment_id}&type=payment"
            ),
            data=json.dumps(
                {
                    "id": "notification-id",
                    "type": "payment",
                    "data": {"id": self.order.external_payment_id},
                }
            ),
            content_type="application/json",
            HTTP_X_SIGNATURE=f"ts={timestamp},v1={signature}",
            HTTP_X_REQUEST_ID=request_id,
        )

        self.assertEqual(response.status_code, 200)
        get_status.assert_called_once_with(self.order.external_payment_id)
        process_notification.assert_called_once()
