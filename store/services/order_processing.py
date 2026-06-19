import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from store.models import Order, OrderItem, PaymentLog, ProviderLog
from store.services.provider_api import ProviderAPIError, submit_order


logger = logging.getLogger(__name__)

PAID_STATUSES = {"paid", "approved", "completed"}


def send_payment_approved_email(order):
    if not order.email:
        return

    subject = "Pagamento aprovado — seu pedido entrou em processamento"
    message = """Olá!

Seu pagamento foi aprovado com sucesso.

Seu pedido já entrou em processamento e será acompanhado pelo nosso sistema.

Obrigado por usar os serviços da WebMaster.

Atenciosamente,
Equipe WebMaster
"""

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [order.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Falha ao enviar e-mail de pagamento aprovado para o pedido %s.", order.code)


def _record_payment_error(order, reason):
    PaymentLog.objects.create(
        order=order,
        event_type=PaymentLog.EventType.ERROR,
        external_payment_id=order.external_payment_id,
        status=Order.PaymentStatus.ERROR,
        amount=order.amount_brl,
        response_data={"reason": reason},
    )


def dispatch_paid_order(order_id, retry_errors=False):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.payment_status != Order.PaymentStatus.PAID:
            return False
        if order.fulfillment_status in {
            Order.FulfillmentStatus.SUBMITTING,
            Order.FulfillmentStatus.SUBMITTED,
        }:
            return order.fulfillment_status == Order.FulfillmentStatus.SUBMITTED
        if (
            order.fulfillment_status == Order.FulfillmentStatus.ERROR
            and not retry_errors
        ):
            return False
        order.fulfillment_status = Order.FulfillmentStatus.SUBMITTING
        order.save(update_fields=("fulfillment_status", "updated_at"))

    item_statuses = [Order.FulfillmentStatus.PENDING]
    if retry_errors:
        item_statuses.append(Order.FulfillmentStatus.ERROR)
    items = list(
        OrderItem.objects.filter(
            order_id=order_id,
            fulfillment_status__in=item_statuses,
        )
    )
    for item in items:
        item.fulfillment_status = Order.FulfillmentStatus.SUBMITTING
        item.save(update_fields=("fulfillment_status",))
        try:
            result = submit_order(item)
        except ProviderAPIError:
            item.fulfillment_status = Order.FulfillmentStatus.ERROR
            item.save(update_fields=("fulfillment_status",))
            ProviderLog.objects.create(
                order_id=order_id,
                level=ProviderLog.Level.ERROR,
                action="submit_error",
                message="Falha ao enviar pedido para processamento.",
                response_data={"reason": "provider_request_failed"},
            )
            Order.objects.filter(pk=order_id).update(
                fulfillment_status=Order.FulfillmentStatus.ERROR
            )
            return False
        item.fulfillment_status = Order.FulfillmentStatus.SUBMITTED
        item.external_order_id = str(result["order"])
        item.external_status = str(result.get("status", "submitted"))
        item.submitted_at = timezone.now()
        item.save(
            update_fields=(
                "fulfillment_status",
                "external_order_id",
                "external_status",
                "submitted_at",
            )
        )

    first_item = OrderItem.objects.filter(order_id=order_id).first()
    Order.objects.filter(pk=order_id).update(
        fulfillment_status=Order.FulfillmentStatus.SUBMITTED,
        external_order_id=first_item.external_order_id if first_item else "",
        provider_status=first_item.external_status if first_item else "submitted",
        submitted_at=timezone.now(),
    )
    return True


def process_payment_notification(data):
    if not data.get("signature_valid"):
        return False

    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                code=data["external_reference"]
            )
        except Order.DoesNotExist:
            return False

        charge = (
            order.payment_logs.filter(event_type=PaymentLog.EventType.CHARGE)
            .order_by("-created_at")
            .first()
        )
        if not charge:
            _record_payment_error(order, "charge_not_found")
            return False
        if (
            charge.external_payment_id != data["external_payment_id"]
            or (
                order.external_payment_id
                and order.external_payment_id != data["external_payment_id"]
            )
        ):
            _record_payment_error(order, "payment_id_mismatch")
            return False
        if charge.amount != data["amount"] or order.amount_brl != data["amount"]:
            _record_payment_error(order, "payment_amount_mismatch")
            return False

        PaymentLog.objects.create(
            order=order,
            event_type=data.get("event_type", PaymentLog.EventType.WEBHOOK),
            external_payment_id=data["external_payment_id"],
            status=data["status"],
            amount=data["amount"],
            signature_valid=data["signature_valid"],
            response_data=data["raw"],
        )

        if data["status"] not in PAID_STATUSES:
            if data["status"] in {
                Order.PaymentStatus.REJECTED,
                Order.PaymentStatus.CANCELLED,
                Order.PaymentStatus.REFUNDED,
            }:
                order.payment_status = data["status"]
                order.save(update_fields=("payment_status", "updated_at"))
            return True

        should_send_approved_email = order.payment_status != Order.PaymentStatus.PAID
        if should_send_approved_email:
            order.mark_paid()
            order.save(update_fields=("payment_status", "paid_at", "updated_at"))
            try:
                from store.services.meta_capi import send_purchase_event
                send_purchase_event(order)
            except Exception:
                logger.exception("CAPI: falha ao enviar Purchase (pagamento nao afetado)")
        order_id = order.id

    if should_send_approved_email:
        send_payment_approved_email(order)

    dispatch_paid_order(order_id)
    return True
