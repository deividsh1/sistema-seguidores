import uuid

import requests
from django.conf import settings

from store.models import ProviderLog
from store.security import sanitized_data


class ProviderAPIError(Exception):
    pass


def provider_request(action, **params):
    if not settings.PROVIDER_API_URL or not settings.PROVIDER_API_KEY:
        raise ProviderAPIError("A integração de entrega não está configurada.")

    payload = {"key": settings.PROVIDER_API_KEY, "action": action, **params}

    try:
        response = requests.post(
            settings.PROVIDER_API_URL,
            data=payload,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise ProviderAPIError("Falha temporária na conexão com a SMMCost.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raw_response = (response.text or "")[:300]
        raise ProviderAPIError(
            f"Resposta inválida da SMMCost. HTTP {response.status_code}. "
            f"Trecho da resposta: {raw_response}"
        ) from exc

    if response.status_code >= 400:
        raise ProviderAPIError(
            f"Falha HTTP na SMMCost: status {response.status_code}. "
            f"Resposta: {str(data)[:300]}"
        )

    if not isinstance(data, (dict, list)):
        raise ProviderAPIError("Resposta inesperada da SMMCost.")

    if isinstance(data, dict) and data.get("error"):
        error_message = str(data.get("error", "Erro desconhecido"))
        raise ProviderAPIError(f"SMMCost recusou a solicitação: {error_message}")

    return data


def list_services():
    return provider_request("services")


def get_balance():
    return provider_request("balance")


def get_order_status(order_id):
    return provider_request("status", order=order_id)


def get_multiple_order_status(order_ids):
    return provider_request("status", orders=_comma_separated_ids(order_ids))


def create_refill(order_id):
    return provider_request("refill", order=order_id)


def create_multiple_refill(order_ids):
    return provider_request("refill", orders=_comma_separated_ids(order_ids))


def get_refill_status(refill_id):
    return provider_request("refill_status", refill=refill_id)


def get_multiple_refill_status(refill_ids):
    return provider_request("refill_status", refills=_comma_separated_ids(refill_ids))


def cancel_orders(order_ids):
    return provider_request("cancel", orders=_comma_separated_ids(order_ids))


def _comma_separated_ids(values):
    if isinstance(values, (str, int)):
        values = [values]
    ids = [str(value).strip() for value in values if str(value).strip()]
    if not ids:
        raise ProviderAPIError("Informe ao menos um ID para a integração de entrega.")
    if len(ids) > 100:
        raise ProviderAPIError("A integração aceita no máximo 100 IDs por solicitação.")
    return ",".join(ids)


def submit_order(order_or_item):
    if settings.PROVIDER_SIMULATED:
        result = {
            "order": f"SIM-{uuid.uuid4().hex[:12].upper()}",
            "status": "simulated",
        }
        ProviderLog.objects.create(
            order=getattr(order_or_item, "order", order_or_item),
            action="submit_simulated",
            message="Pedido processado em modo simulado.",
            response_data=result,
        )
        return result

    provider_service_id = getattr(order_or_item, "provider_service_id", "")
    if not provider_service_id:
        raise ProviderAPIError("O pedido não possui ID técnico de serviço.")

    parameters = {
        "service": provider_service_id,
        "link": order_or_item.target,
        "quantity": order_or_item.quantity,
    }
    comments_text = getattr(order_or_item, "comments_text", "").strip()
    if comments_text:
        parameters["comments"] = comments_text
    data = provider_request("add", **parameters)
    if not isinstance(data, dict):
        raise ProviderAPIError("Resposta inválida da integração de entrega.")
    external_id = data.get("order")
    if not external_id:
        raise ProviderAPIError("A integração não retornou o ID do pedido.")

    ProviderLog.objects.create(
        order=getattr(order_or_item, "order", order_or_item),
        action="submit",
        message="Pedido enviado para processamento.",
        response_data=sanitized_data(
            {"order": str(external_id), "status": data.get("status", "")}
        ),
    )
    return {"order": str(external_id), "status": data.get("status", "submitted")}
