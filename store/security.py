import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def get_client_ip(request):
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def rate_limit(request, scope, limit, window_seconds, identifier=""):
    source = f"{get_client_ip(request)}:{identifier}".encode()
    digest = hashlib.sha256(source).hexdigest()
    key = f"rate-limit:{scope}:{digest}"
    if cache.add(key, 1, timeout=window_seconds):
        return True
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        attempts = 1
    return attempts <= limit


def sanitized_data(data):
    sensitive_fragments = (
        "key",
        "token",
        "secret",
        "authorization",
        "password",
        "email",
        "phone",
        "whatsapp",
        "customer",
        "target",
        "link",
        "pix",
        "qr_code",
        "copy_paste",
        "comments",
    )
    if isinstance(data, dict):
        return {
            key: (
                "[protegido]"
                if any(fragment in key.lower() for fragment in sensitive_fragments)
                else sanitized_data(value)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [sanitized_data(value) for value in data[:100]]
    return data


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path.startswith("/admin/login/")
            and request.method == "POST"
            and not rate_limit(request, "admin-login", 10, 900)
        ):
            return HttpResponse("Tente novamente mais tarde.", status=429)
        response = self.get_response(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://connect.facebook.net; "
            "style-src 'self' https://cdn.jsdelivr.net; "
            "style-src-attr 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://connect.facebook.net https://www.facebook.com; "
            "frame-ancestors 'none'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        if request.path.startswith(
            ("/checkout/", "/pagamento/", "/pedido/", "/webhooks/", "/api/profile-preview/")
        ):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
