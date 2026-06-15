from django.core.management.base import BaseCommand, CommandError

from store.models import Order
from store.services.payment_api import PaymentAPIError, get_payment_status


class Command(BaseCommand):
    help = "Consulta o status de um pagamento no Mercado Pago sem alterar o banco."

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

        self.stdout.write(f"Código do pedido: {order.code}")
        self.stdout.write(f"Status do pedido: {order.payment_status}")
        self.stdout.write(f"Payment ID externo: {payment_id}")
        self.stdout.write(
            f"PaymentLog mais recente: {payment_log.event_type} / "
            f"{payment_log.status or 'sem status'}"
        )
        payment_url = payment_log.payment_url or (
            order.payment_logs.exclude(payment_url="")
            .order_by("-created_at", "-pk")
            .values_list("payment_url", flat=True)
            .first()
        )
        if payment_url:
            self.stdout.write(f"Payment URL: {payment_url}")

        try:
            payment = get_payment_status(payment_id)
        except PaymentAPIError as exc:
            raise CommandError(f"Falha ao consultar o Mercado Pago: {exc}") from exc

        self.stdout.write(f"Status Mercado Pago: {payment['status'] or 'sem status'}")
        self.stdout.write(
            f"External reference Mercado Pago: "
            f"{payment['external_reference'] or 'não informada'}"
        )
        self.stdout.write(f"Valor Mercado Pago: {payment['amount']}")
        self.stdout.write(self.style.SUCCESS("Consulta concluída sem alterar o banco."))
