import re
from urllib.parse import quote

from django.conf import settings


DEFAULT_SUPPORT_MESSAGE = "Olá, preciso de ajuda com meu pedido WebMaster."


def build_whatsapp_url(message=DEFAULT_SUPPORT_MESSAGE):
    number = re.sub(r"\D", "", settings.WHATSAPP_SUPPORT_NUMBER)
    if not number:
        return ""
    return f"https://wa.me/{number}?text={quote(message)}"


def commercial_settings(request):
    return {
        "social_proof_enabled": settings.SOCIAL_PROOF_ENABLED,
        "whatsapp_support_url": build_whatsapp_url(),
    }
