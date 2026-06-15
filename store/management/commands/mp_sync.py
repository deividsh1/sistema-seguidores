from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from store.models import Order, PaymentLog
from store.services.order_processing import process_payment_notification
from store.services.payment_api import PaymentAPIError, get_payment_status


class Command(BaseCommand):
    help = "Sincroniza um pagamento aprovado no Mercado Pago com o pedido local."

    def add_arguments(self, parser):
        parser.add_argument("code", help="Código público do pedido")

    def handle(self, *args, **options):
        code = options["code"].strip().upper()
        try:
            order = Order.objects.get(code=code)
        except Order.DoesNotExist as exc:
            raise CommandError(f"Pedido {code} não encontrado.") from exc

        payment_log = order.payment_logs.order_by("-created_at", "-pk").first()
        if not payment_log:
            raise CommandError(f"Pedido {order.code} não possui PaymentLog.")

        payment_id = order.external_payment_id or payment_log.external_payment_id
        if not payment_id:
            raise CommandError(f"Pedido {order.code} não possui payment ID externo.")

        try:
            payment = get_payment_status(payment_id)
        except PaymentAPIError as exc:
            raise CommandError(f"Falha ao consultar o Mercado Pago: {exc}") from exc

        if payment["external_reference"] != order.code:
            raise CommandError(
                "External reference do Mercado Pago não corresponde ao código do pedido."
            )

        status = payment["status"]
        self.stdout.write(f"Pedido: {order.code}")
        self.stdout.write(f"Payment ID externo: {payment_id}")
        self.stdout.write(f"Status Mercado Pago: {status or 'sem status'}")

        if status == "pending":
            self.stdout.write(
                self.style.WARNING(
                    "O pagamento continua pendente. Nenhuma alteração foi realizada."
                )
            )
            return

        if status in {"rejected", "cancelled", "expired"}:
            self.stdout.write(
                self.style.WARNING(
                    f"Pagamento {status}. O pedido não foi marcado como pago."
                )
            )
            return

        if status != "approved":
            self.stdout.write(
                self.style.WARNING(
                    f"Status {status or 'desconhecido'} não sincronizado. "
                    "Nenhuma alteração foi realizada."
                )
            )
            return

        payment.update(
            {
                "signature_valid": True,
                "event_type": PaymentLog.EventType.STATUS,
            }
        )
        if not process_payment_notification(payment):
            raise CommandError(
                "O pagamento foi aprovado, mas os dados divergiram do pedido local."
            )

        order.refresh_from_db()
        provider_mode = "simulado" if settings.PROVIDER_SIMULATED else "real"
        self.stdout.write(
            self.style.SUCCESS(
                f"Pedido sincronizado: {order.payment_status} / "
                f"{order.fulfillment_status}. Provedor: {provider_mode}."
            )
        )
