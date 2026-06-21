import logging
import re

from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from store.context_processors import build_whatsapp_url
from store.forms import OrderForm, OrderLookupForm
from store.models import Order, Package, PaymentLog, Platform, ProviderLog, Service
from store.security import rate_limit
from store.services.order_processing import process_payment_notification
from store.services.payment_api import (
    LegacyPaymentNotificationError,
    PaymentAPIError,
    PaymentWebhookValidationError,
    create_pix_charge,
    get_payment_status,
    parse_payment_webhook,
)
from store.services.profile_lookup import (
    ProfileLookupError,
    lookup_profile,
    list_recent_media,
)
from store.services.provider_api import ProviderAPIError, get_order_status


logger = logging.getLogger(__name__)


def too_many_requests(request):
    return render(request, "store/rate_limited.html", status=429)


def home(request):
    return render(
        request, "store/home.html", {"platforms": Platform.objects.filter(active=True)}
    )


def digital_services(request):
    return render(
        request,
        "store/digital_services.html",
        {"platforms": Platform.objects.filter(active=True)},
    )


def how_to_order(request):
    return render(request, "store/how_to_order.html")


def platform_detail(request, slug):
    packages = Package.objects.filter(active=True).order_by("position", "quantity")
    platform = get_object_or_404(
        Platform.objects.prefetch_related(
            Prefetch(
                "services",
                queryset=Service.objects.filter(active=True).prefetch_related(
                    Prefetch("packages", queryset=packages)
                ),
            )
        ),
        slug=slug,
        active=True,
    )
    return render(request, "store/platform.html", {"platform": platform})


def checkout(request, package_id):
    package = get_object_or_404(
        Package.objects.select_related("service__platform"),
        pk=package_id,
        active=True,
        service__active=True,
        service__provider_service_id__gt="",
        service__platform__active=True,
    )
    if request.method == "POST" and not rate_limit(request, "checkout-ip", 8, 3600):
        return too_many_requests(request)

    form = OrderForm(request.POST or None, package=package, request=request)
    if request.method == "POST" and form.is_valid():
        contact_key = f"{form.cleaned_data['whatsapp']}:{form.cleaned_data.get('email', '')}"
        if not rate_limit(request, "checkout-contact", 3, 3600, contact_key):
            return too_many_requests(request)

        with transaction.atomic():
            order = form.save()
            fbp = request.POST.get("fb_fbp", "")[:255]
            fbc = request.POST.get("fb_fbc", "")[:255]
            if fbp or fbc:
                order.fb_fbp = fbp
                order.fb_fbc = fbc
                order.save(update_fields=("fb_fbp", "fb_fbc", "updated_at"))
        try:
            charge = create_pix_charge(order)
            order.external_payment_id = charge["id"]
            order.save(update_fields=("external_payment_id", "updated_at"))
            PaymentLog.objects.create(
                order=order,
                event_type=PaymentLog.EventType.CHARGE,
                external_payment_id=charge["id"],
                status=charge["status"],
                amount=order.amount_brl,
                pix_code=charge["pix_code"],
                qr_code_base64=charge["qr_code_base64"],
                payment_url=charge["payment_url"],
                response_data=charge["raw"],
            )
            try:
                from store.services.meta_capi import send_add_payment_info_event
                send_add_payment_info_event(order)
            except Exception:
                logger.exception("CAPI: falha ao enviar AddPaymentInfo (checkout nao afetado)")
        except PaymentAPIError:
            logger.warning("Falha ao gerar cobrança Pix para o pedido %s.", order.code)
            order.payment_status = Order.PaymentStatus.ERROR
            order.save(update_fields=("payment_status", "updated_at"))
            PaymentLog.objects.create(
                order=order,
                event_type=PaymentLog.EventType.ERROR,
                status=Order.PaymentStatus.ERROR,
                amount=order.amount_brl,
                response_data={"message": "Falha ao gerar cobrança Pix."},
            )
            messages.error(
                request,
                "O pedido foi criado, mas não foi possível gerar o Pix. "
                "Tente novamente mais tarde usando o código do pedido.",
            )
        return redirect("store:payment", code=order.code)
    if request.method == "POST":
        logger.info(
            "Checkout inválido para o pacote %s. Campos: %s",
            package.id,
            ", ".join(form.errors.keys()),
        )

    selected_upsells = {
        str(value) for value in request.POST.getlist("upsells")
    } if request.method == "POST" else set()
    sibling_packages = Package.objects.filter(
        service=package.service,
        active=True,
    ).order_by("position", "quantity")
    if request.method == "GET":
        try:
            from store.services.meta_capi import send_initiate_checkout_event
            _fbp = request.COOKIES.get("_fbp", "")
            _fbc = request.COOKIES.get("_fbc", "")
            send_initiate_checkout_event(request, package, fbp=_fbp, fbc=_fbc)
        except Exception:
            logger.exception("CAPI: falha ao enviar InitiateCheckout (pagina nao afetada)")
    return render(
        request,
        "store/checkout.html",
        {
            "package": package,
            "form": form,
            "sibling_packages": sibling_packages,
            "upsell_packages": form.fields["upsells"].queryset,
            "selected_upsells": selected_upsells,
        },
    )


def payment(request, code):
    order = get_object_or_404(Order, code=code.upper())
    payment_log = order.payment_logs.filter(
        event_type=PaymentLog.EventType.CHARGE
    ).first()
    return render(
        request,
        "store/payment.html",
        {
            "order": order,
            "payment_log": payment_log,
            "can_verify_payment": bool(
                order.external_payment_id
                and not order.external_payment_id.startswith("SIM-")
                and order.payment_status != Order.PaymentStatus.PAID
            ),
        },
    )


@require_POST
def verify_payment(request, code):
    if not rate_limit(request, "verify-payment", 8, 300):
        return too_many_requests(request)

    order = get_object_or_404(Order, code=code.upper())
    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("store:payment", code=order.code)
    if not order.external_payment_id or order.external_payment_id.startswith("SIM-"):
        messages.info(request, "A verificação externa não está disponível para este pagamento.")
        return redirect("store:payment", code=order.code)

    try:
        data = get_payment_status(order.external_payment_id)
        data.update(
            {
                "signature_valid": True,
                "event_type": PaymentLog.EventType.STATUS,
            }
        )
        accepted = process_payment_notification(data)
    except PaymentAPIError:
        logger.warning("Falha ao consultar pagamento do pedido %s.", order.code)
        PaymentLog.objects.create(
            order=order,
            event_type=PaymentLog.EventType.ERROR,
            external_payment_id=order.external_payment_id,
            status=Order.PaymentStatus.ERROR,
            amount=order.amount_brl,
            response_data={"reason": "payment_status_request_failed"},
        )
        messages.error(request, "Não foi possível verificar o pagamento agora.")
    else:
        order.refresh_from_db()
        if not accepted:
            messages.error(request, "O pagamento consultado não corresponde ao pedido.")
        elif order.payment_status == Order.PaymentStatus.PAID:
            messages.success(request, "Pagamento aprovado.")
        else:
            messages.info(request, "Pagamento ainda não aprovado. Aguarde alguns instantes.")
    return redirect("store:payment", code=order.code)


def success(request, code):
    order = get_object_or_404(Order, code=code.upper())
    return render(
        request,
        "store/success.html",
        {
            "order": order,
            "whatsapp_order_url": build_whatsapp_url(
                f"Olá, preciso de ajuda com meu pedido WebMaster. Código: {order.code}"
            ),
        },
    )


def order_lookup(request):
    if request.method == "POST" and not rate_limit(request, "order-lookup", 12, 600):
        return too_many_requests(request)

    form = OrderLookupForm(request.POST or None)
    order = None
    searched = request.method == "POST"
    if searched and form.is_valid():
        candidate = Order.objects.filter(code=form.cleaned_data["code"]).first()
        if candidate:
            contact = form.cleaned_data["contact"].strip()
            digits = re.sub(r"\D", "", contact)
            matches_email = bool(candidate.email) and candidate.email.lower() == contact.lower()
            matches_whatsapp = bool(digits) and candidate.whatsapp == digits
            if matches_email or matches_whatsapp:
                order = candidate
                if candidate.external_order_id and not candidate.external_order_id.startswith(
                    "SIM-"
                ):
                    try:
                        data = get_order_status(candidate.external_order_id)
                        candidate.provider_status = str(data.get("status", ""))
                        candidate.save(update_fields=("provider_status", "updated_at"))
                    except ProviderAPIError:
                        ProviderLog.objects.create(
                            order=candidate,
                            level=ProviderLog.Level.ERROR,
                            action="status_error",
                            message="Falha ao consultar andamento do pedido.",
                            response_data={"reason": "provider_status_request_failed"},
                        )

    return render(
        request,
        "store/order_lookup.html",
        {"form": form, "order": order, "searched": searched},
    )


@require_GET
def profile_preview(request):
    if not rate_limit(request, "profile-preview", 30, 300):
        return JsonResponse(
            {
                "ok": False,
                "status": "unknown",
                "username": "",
                "profile_picture_url": "",
                "is_public": None,
                "message": "Não foi possível verificar o perfil agora. Tente novamente mais tarde.",
            },
            status=429,
        )

    platform = request.GET.get("platform", "").strip().lower()
    target = request.GET.get("target", "").strip()
    if not target or len(target) > 500:
        return JsonResponse(
            {
                "ok": False,
                "status": "not_found",
                "username": "",
                "profile_picture_url": "",
                "is_public": False,
                "message": (
                    "Não conseguimos acessar esse perfil. Verifique se o @ está correto "
                    "e deixe o perfil público para receber o pedido."
                ),
            },
            status=400,
        )
    try:
        return JsonResponse(lookup_profile(platform, target))
    except ProfileLookupError as exc:
        return JsonResponse(
            {
                "ok": False,
                "status": "not_found",
                "username": "",
                "profile_picture_url": "",
                "is_public": False,
                "message": str(exc),
            },
            status=400,
        )


@require_GET
def profile_media(request):
    if not rate_limit(request, "profile-media", 30, 300):
        return JsonResponse({"ok": False, "items": [], "message": "Tente novamente mais tarde."}, status=429)

    platform = request.GET.get("platform", "").strip().lower()
    target = request.GET.get("target", "").strip()
    if not target or len(target) > 500:
        return JsonResponse({"ok": False, "items": [], "message": "Parâmetros inválidos."}, status=400)

    # Validate format first
    try:
        # reuse lookup_profile for format validation side-effect
        profile = lookup_profile(platform, target)
    except ProfileLookupError:
        return JsonResponse({"ok": False, "items": [], "message": "Formato inválido."}, status=400)

    if profile.get("status") == "invalid":
        return JsonResponse({"ok": False, "items": [], "message": "Formato inválido."}, status=400)

    username = profile.get("username", "")
    media = list_recent_media(platform, username)
    return JsonResponse(media)


@csrf_exempt
@require_POST
def mercadopago_webhook(request):
    if not rate_limit(request, "payment-webhook", 180, 60):
        return JsonResponse({"error": "try later"}, status=429)
    try:
        data = parse_payment_webhook(request)
    except LegacyPaymentNotificationError as exc:
        already_processed = Order.objects.filter(
            external_payment_id=exc.payment_id,
            payment_status=Order.PaymentStatus.PAID,
            payment_logs__external_payment_id=exc.payment_id,
            payment_logs__status__in=("paid", "approved", "completed"),
            payment_logs__signature_valid=True,
        ).exists()
        if already_processed:
            logger.info(
                "Notificação IPN legada duplicada ignorada: payment_id=%s topic=payment.",
                exc.payment_id,
            )
            return HttpResponse(status=200)
        logger.warning("Notificação IPN legada rejeitada por validação.")
        return JsonResponse({"error": "invalid webhook"}, status=401)
    except PaymentWebhookValidationError:
        logger.warning("Webhook de pagamento rejeitado por validação.")
        return JsonResponse({"error": "invalid webhook"}, status=401)
    except PaymentAPIError:
        logger.warning("Não foi possível confirmar o pagamento notificado.")
        return JsonResponse({"error": "temporary failure"}, status=503)
    if not process_payment_notification(data):
        logger.warning("Webhook de pagamento rejeitado por divergência.")
        return JsonResponse({"error": "payment mismatch"}, status=400)
    logger.info(
        "Webhook de pagamento aceito: payment_id=%s type=payment.",
        data.get("external_payment_id", ""),
    )
    return HttpResponse(status=200)


payment_webhook = mercadopago_webhook


def terms(request):
    return render(request, "store/terms.html")
