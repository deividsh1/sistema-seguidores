from django.core.management.base import BaseCommand, CommandError

from store.models import Order, PaymentLog
from store.services.order_processing import process_payment_notification


class Command(BaseCommand):
    help = "Aprova um pagamento simulado e processa o pedido."

    def add_arguments(self, parser):
        parser.add_argument("code", help="Código público do pedido")

    def handle(self, *args, **options):
        try:
            order = Order.objects.get(code=options["code"].upper())
            payment = order.payment_logs.filter(
                event_type=PaymentLog.EventType.CHARGE
            ).first()
            if not payment:
                raise PaymentLog.DoesNotExist
        except (Order.DoesNotExist, PaymentLog.DoesNotExist) as exc:
            raise CommandError("Pedido ou pagamento não encontrado.") from exc

        data = {
            "external_payment_id": payment.external_payment_id,
            "status": "approved",
            "external_reference": order.code,
            "amount": order.amount_brl,
            "signature_valid": True,
            "raw": {"mode": "simulated"},
        }
        if not process_payment_notification(data):
            raise CommandError("Não foi possível aprovar o pagamento.")
        order.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"Pedido {order.code}: {order.get_payment_status_display()} / "
                f"{order.get_fulfillment_status_display()}."
            )
        )
