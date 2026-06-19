import os
from pathlib import Path

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


DEBUG = env_bool("DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key-change-me")
if not DEBUG and SECRET_KEY == "unsafe-development-key-change-me":
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY em produção.")
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "anymail",
    "store",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "store.security.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.commercial_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=60,
            ssl_require=True,
        )
    }
elif os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "")
PROVIDER_API_URL = os.getenv("PROVIDER_API_URL", "").rstrip("/")
PROVIDER_SIMULATED = env_bool("PROVIDER_SIMULATED", DEBUG)

PROFILE_LOOKUP_PROVIDER = os.getenv("PROFILE_LOOKUP_PROVIDER", "simulated").strip().lower()
PROFILE_LOOKUP_API_URL = os.getenv("PROFILE_LOOKUP_API_URL", "").rstrip("/")
PROFILE_LOOKUP_API_KEY = os.getenv("PROFILE_LOOKUP_API_KEY", "")
PROFILE_LOOKUP_TIMEOUT = int(os.getenv("PROFILE_LOOKUP_TIMEOUT", "10"))
PROFILE_LOOKUP_SIMULATED = env_bool("PROFILE_LOOKUP_SIMULATED", PROFILE_LOOKUP_PROVIDER == "simulated")

PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "mercadopago").strip().lower()
PAYMENT_SIMULATED = env_bool("PAYMENT_SIMULATED", DEBUG)
MERCADO_PAGO_API_URL = os.getenv(
    "MERCADO_PAGO_API_URL", "https://api.mercadopago.com"
).rstrip("/")
MERCADO_PAGO_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "")
MERCADO_PAGO_PUBLIC_KEY = os.getenv("MERCADO_PAGO_PUBLIC_KEY", "")
MERCADO_PAGO_WEBHOOK_SECRET = os.getenv("MERCADO_PAGO_WEBHOOK_SECRET", "")
MERCADO_PAGO_WEBHOOK_TOLERANCE_SECONDS = int(
    os.getenv("MERCADO_PAGO_WEBHOOK_TOLERANCE_SECONDS", "600")
)
# Mantido apenas para aprovar webhooks simulados em desenvolvimento/testes.
PAYMENT_WEBHOOK_SECRET = os.getenv(
    "PAYMENT_WEBHOOK_SECRET", MERCADO_PAGO_WEBHOOK_SECRET
)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# Meta CAPI (API de Conversoes)
META_PIXEL_ID = os.getenv("META_PIXEL_ID", "")
META_CAPI_TOKEN = os.getenv("META_CAPI_TOKEN", "")
ORDER_EMAIL_REQUIRED = env_bool("ORDER_EMAIL_REQUIRED", True)
TRUST_X_FORWARDED_FOR = env_bool("TRUST_X_FORWARDED_FOR", False)
WHATSAPP_SUPPORT_NUMBER = os.getenv(
    "WHATSAPP_SUPPORT_NUMBER", "+5518996650268"
).strip()
SOCIAL_PROOF_ENABLED = env_bool("SOCIAL_PROOF_ENABLED", True)

if not PAYMENT_SIMULATED:
    if PAYMENT_PROVIDER != "mercadopago":
        raise ImproperlyConfigured("PAYMENT_PROVIDER deve ser mercadopago.")
    if not all((MERCADO_PAGO_ACCESS_TOKEN, MERCADO_PAGO_WEBHOOK_SECRET, PUBLIC_BASE_URL)):
        raise ImproperlyConfigured(
            "Configure Mercado Pago e PUBLIC_BASE_URL antes de desativar PAYMENT_SIMULATED."
        )
    if len(MERCADO_PAGO_WEBHOOK_SECRET) < 24:
        raise ImproperlyConfigured(
            "MERCADO_PAGO_WEBHOOK_SECRET deve ter ao menos 24 caracteres."
        )
if not PROVIDER_SIMULATED and not all((PROVIDER_API_URL, PROVIDER_API_KEY)):
    raise ImproperlyConfigured(
        "Configure PROVIDER_API_URL e PROVIDER_API_KEY antes de desativar PROVIDER_SIMULATED."
    )
if not DEBUG:
    for setting_name, value in (
        ("PUBLIC_BASE_URL", PUBLIC_BASE_URL),
        ("MERCADO_PAGO_API_URL", MERCADO_PAGO_API_URL if not PAYMENT_SIMULATED else ""),
        ("PROVIDER_API_URL", PROVIDER_API_URL if not PROVIDER_SIMULATED else ""),
    ):
        if value and not value.startswith("https://"):
            raise ImproperlyConfigured(f"{setting_name} deve usar HTTPS em produção.")

CACHES = {
    "default": {
        "BACKEND": os.getenv(
            "CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": os.getenv("CACHE_LOCATION", "webmaster-rate-limit"),
    }
}

if env_bool("TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SAMESITE = "Lax"
PASSWORD_RESET_TIMEOUT = 1800
DATA_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "WebMaster <no-reply@webmaster.local>")

if DEBUG:
    EMAIL_BACKEND = os.getenv(
        "EMAIL_BACKEND",
        "django.core.mail.backends.console.EmailBackend",
    )
else:
    EMAIL_BACKEND = os.getenv(
        "EMAIL_BACKEND",
        "anymail.backends.brevo.EmailBackend",
    )
    EMAIL_HOST = os.getenv("EMAIL_HOST", "")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)

ANYMAIL = {
    "BREVO_API_KEY": os.getenv("BREVO_API_KEY", ""),
}
