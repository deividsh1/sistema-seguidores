"""
Integração com a API de Conversões da Meta (CAPI).

Módulo ISOLADO: toda a lógica de envio de eventos para a Meta fica aqui, fora
do código de pagamento. Se algo falhar aqui, o pagamento NÃO é afetado — quem
chama deve envolver em try/except.

Evento: Purchase (server-side), no momento em que o pedido vira pago.
Deduplicação: event_id = order.code (a Meta junta com o pixel do navegador).
"""

import hashlib
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_GRAPH_API_VERSION = "v19.0"
_TIMEOUT_SECONDS = 8


def _hash(value):
    if not value:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _hash_phone(value):
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    if len(digits) in (10, 11):
        digits = "55" + digits
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()


def send_purchase_event(order, test_event_code=None):
    pixel_id = getattr(settings, "META_PIXEL_ID", "")
    token = getattr(settings, "META_CAPI_TOKEN", "")

    if not pixel_id or not token:
        logger.warning("CAPI: META_PIXEL_ID ou META_CAPI_TOKEN ausente; evento nao enviado.")
        return False

    user_data = {}

    email_hash = _hash(getattr(order, "email", ""))
    if email_hash:
        user_data["em"] = [email_hash]

    phone_hash = _hash_phone(getattr(order, "whatsapp", ""))
    if phone_hash:
        user_data["ph"] = [phone_hash]

    client_ip = getattr(order, "customer_ip", "")
    if client_ip:
        user_data["client_ip_address"] = client_ip

    user_agent = getattr(order, "customer_user_agent", "")
    if user_agent:
        user_data["client_user_agent"] = user_agent

    try:
        value = float(order.amount_brl)
    except (TypeError, ValueError):
        value = 0.0

    base_url = getattr(settings, "PUBLIC_BASE_URL", "") or ""
    event_source_url = None
    if base_url:
        event_source_url = base_url.rstrip("/") + "/pedido/" + str(order.code) + "/sucesso/"

    event = {
        "event_name": "Purchase",
        "event_time": int(time.time()),
        "action_source": "website",
        "event_id": str(order.code),
        "user_data": user_data,
        "custom_data": {
            "currency": "BRL",
            "value": round(value, 2),
        },
    }
    if event_source_url:
        event["event_source_url"] = event_source_url

    payload = {"data": [event]}
    if test_event_code:
        payload["test_event_code"] = test_event_code

    url = (
        "https://graph.facebook.com/"
        + _GRAPH_API_VERSION
        + "/"
        + str(pixel_id)
        + "/events"
    )

    try:
        response = requests.post(
            url,
            params={"access_token": token},
            json=payload,
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("CAPI: erro de rede ao enviar Purchase do pedido %s: %s", order.code, exc)
        return False

    if response.status_code == 200:
        logger.info("CAPI: Purchase enviado para o pedido %s (valor R$ %.2f).", order.code, value)
        return True

    logger.warning(
        "CAPI: Meta recusou Purchase do pedido %s. HTTP %s - %s",
        order.code,
        response.status_code,
        response.text[:500],
    )
    return False
