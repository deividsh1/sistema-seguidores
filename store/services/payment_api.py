import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.urls import reverse

from store.security import sanitized_data


class PaymentAPIError(Exception):
    pass


class PaymentWebhookValidationError(PaymentAPIError):
    pass


class LegacyPaymentNotificationError(PaymentWebhookValidationError):
    def __init__(self, payment_id):
        super().__init__("Notificação IPN legada sem validação de origem suportada.")
        self.payment_id = payment_id


def _mercado_pago_headers(idempotency_key=""):
    headers = {
        "Authorization": f"Bearer {settings.MERCADO_PAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return headers


def _mercado_pago_idempotency_key(order):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"webmaster-payment:{order.code}"))


def _webhook_url():
    base_url = (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if not base_url:
        return ""

    # Em desenvolvimento local, não envie notification_url para o Mercado Pago.
    # O Mercado Pago não consegue chamar 127.0.0.1/localhost.
    # Quando usar ngrok/deploy com HTTPS, PUBLIC_BASE_URL ativa o webhook.
    local_hosts = ("http://127.0.0.1", "http://localhost", "http://0.0.0.0")
    if base_url.startswith(local_hosts):
        return ""

    return f"{base_url}{reverse('store:mercadopago_webhook')}"


def _normalize_mercado_pago_payment(data):
    if not isinstance(data, dict):
        raise PaymentAPIError("O gateway retornou uma resposta inválida.")

    transaction_data = (
        data.get("point_of_interaction", {}).get("transaction_data", {}) or {}
    )
    try:
        amount = Decimal(str(data.get("transaction_amount")))
    except (InvalidOperation, TypeError) as exc:
        raise PaymentAPIError("O gateway retornou um valor inválido.") from exc

    return {
        "id": str(data.get("id") or ""),
        "external_payment_id": str(data.get("id") or ""),
        "external_reference": str(data.get("external_reference") or "").upper(),
        "status": str(data.get("status") or "").lower(),
        "amount": amount,
        "pix_code": transaction_data.get("qr_code") or "",
        "qr_code_base64": transaction_data.get("qr_code_base64") or "",
        "payment_url": transaction_data.get("ticket_url") or "",
        "raw": sanitized_data(data),
    }


def _request_mercado_pago(method, path, **kwargs):
    if not settings.MERCADO_PAGO_ACCESS_TOKEN:
        raise PaymentAPIError("O Mercado Pago não está configurado.")
    try:
        response = requests.request(
            method,
            f"{settings.MERCADO_PAGO_API_URL}{path}",
            timeout=20,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PaymentAPIError("Falha temporária ao comunicar com o Mercado Pago.") from exc


def create_pix_charge(order):
    if settings.PAYMENT_SIMULATED:
        return {
            "id": f"SIM-{uuid.uuid4().hex[:12].upper()}",
            "status": "pending",
            "pix_code": f"PIX-SIMULADO-{order.code}",
            "qr_code_base64": "",
            "payment_url": "",
            "raw": {"mode": "simulated", "order_code": order.code},
        }

    if settings.PAYMENT_PROVIDER != "mercadopago":
        raise PaymentAPIError("O provedor de pagamento configurado não é suportado.")
    if not order.email:
        raise PaymentAPIError("O email do cliente é obrigatório para gerar o Pix.")

    payload = {
        "transaction_amount": float(order.amount_brl),
        "description": f"{order.service_name} - {order.code}",
        "payment_method_id": "pix",
        "external_reference": order.code,
        "payer": {"email": order.email},
    }
    webhook_url = _webhook_url()
    if webhook_url:
        payload["notification_url"] = webhook_url

    data = _request_mercado_pago(
        "POST",
        "/v1/payments",
        json=payload,
        headers=_mercado_pago_headers(_mercado_pago_idempotency_key(order)),
    )
    result = _normalize_mercado_pago_payment(data)
    if not result["id"] or not result["pix_code"]:
        raise PaymentAPIError("O Mercado Pago retornou uma cobrança Pix incompleta.")
    return result


def get_payment_status(external_payment_id):
    if settings.PAYMENT_SIMULATED:
        raise PaymentAPIError("Consulta externa indisponível no modo simulado.")
    if settings.PAYMENT_PROVIDER != "mercadopago":
        raise PaymentAPIError("O provedor de pagamento configurado não é suportado.")

    data = _request_mercado_pago(
        "GET",
        f"/v1/payments/{external_payment_id}",
        headers=_mercado_pago_headers(),
    )
    result = _normalize_mercado_pago_payment(data)
    if result["id"] != str(external_payment_id):
        raise PaymentAPIError("O Mercado Pago retornou um pagamento divergente.")
    return result


def _parse_json_body(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError as exc:
        raise PaymentWebhookValidationError("Webhook inválido.") from exc
    if not isinstance(payload, dict):
        raise PaymentWebhookValidationError("Webhook inválido.")
    return payload


def _validate_mercado_pago_signature(request, data_id):
    signature = request.headers.get("X-Signature", "")
    request_id = request.headers.get("X-Request-Id", "")
    parts = {}
    for part in signature.split(","):
        key, separator, value = part.strip().partition("=")
        if separator:
            parts[key] = value

    timestamp = parts.get("ts", "")
    received_hash = parts.get("v1", "")
    secret = settings.MERCADO_PAGO_WEBHOOK_SECRET
    if not all((data_id, request_id, timestamp, received_hash, secret)):
        return False
    try:
        signature_time = int(timestamp)
    except ValueError:
        return False
    if signature_time > 10_000_000_000:
        signature_time //= 1000
    if abs(int(time.time()) - signature_time) > settings.MERCADO_PAGO_WEBHOOK_TOLERANCE_SECONDS:
        return False

    manifest = f"id:{data_id.lower()};request-id:{request_id};ts:{timestamp};"
    expected_hash = hmac.new(
        secret.encode(), manifest.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(received_hash, expected_hash)


def _parse_simulated_webhook(request):
    secret = settings.PAYMENT_WEBHOOK_SECRET
    received_secret = request.headers.get("X-Webhook-Secret", "")
    if not secret or not hmac.compare_digest(received_secret, secret):
        raise PaymentWebhookValidationError("Webhook não autenticado.")

    payload = _parse_json_body(request)
    try:
        amount = Decimal(str(payload.get("amount") or payload.get("transaction_amount")))
    except (InvalidOperation, TypeError) as exc:
        raise PaymentWebhookValidationError("Webhook sem valor válido.") from exc

    return {
        "external_payment_id": str(payload.get("id") or ""),
        "external_reference": str(payload.get("external_reference") or "").upper(),
        "status": str(payload.get("status") or "").lower(),
        "amount": amount,
        "signature_valid": True,
        "event_type": "webhook",
        "raw": sanitized_data(payload),
    }


def parse_payment_webhook(request):
    if settings.PAYMENT_SIMULATED:
        return _parse_simulated_webhook(request)
    if settings.PAYMENT_PROVIDER != "mercadopago":
        raise PaymentAPIError("O provedor de pagamento configurado não é suportado.")

    payload = _parse_json_body(request)
    data_id = str(request.GET.get("data.id") or payload.get("data", {}).get("id") or "")
    notification_type = str(
        request.GET.get("type") or payload.get("type") or ""
    ).lower()
    legacy_topic = str(request.GET.get("topic") or payload.get("topic") or "").lower()
    legacy_id = str(
        request.GET.get("id") or (payload.get("id") if legacy_topic else "") or ""
    )

    if data_id or notification_type:
        if notification_type != "payment" or not data_id:
            raise PaymentWebhookValidationError("Tipo de webhook não suportado.")
        if not _validate_mercado_pago_signature(request, data_id):
            raise PaymentWebhookValidationError("Webhook não autenticado.")
    elif legacy_id or legacy_topic:
        if legacy_topic != "payment" or not legacy_id or len(legacy_id) > 120:
            raise PaymentWebhookValidationError("Tipo de webhook não suportado.")
        # O Mercado Pago não permite validar a origem de IPNs legadas pela chave
        # secreta. A view só confirma duplicatas já aprovadas localmente.
        raise LegacyPaymentNotificationError(legacy_id)
    else:
        raise PaymentWebhookValidationError("Tipo de webhook não suportado.")

    payment = get_payment_status(data_id)
    payment.update(
        {
            "signature_valid": True,
            "event_type": "webhook",
            "raw": {
                "notification": sanitized_data(payload),
                "payment": payment["raw"],
            },
        }
    )
    return payment


def parse_webhook(request):
    """Compatibilidade para chamadas antigas."""
    return parse_payment_webhook(request)
