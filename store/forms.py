import re
from decimal import Decimal

from django import forms
from django.conf import settings
from django.utils import timezone

from store.models import Order, OrderItem, Package, TERMS_VERSION
from store.security import get_client_ip
from store.services.catalog import get_bonus_options_for_package, get_checkout_complements
from store.services.profile_validation import (
    validate_target_for_service,
    normalize_target_for_service,
)


def target_field_config(service):
    name = service.name.lower()
    if service.requires_comments or "coment" in name:
        return {
            "kind": "comments",
            "label": "Link do vídeo ou publicação",
            "placeholder": "Cole o link do vídeo, Reels ou publicação",
            "help": "Use o link exato do conteúdo que receberá os comentários.",
        }
    if "curtida" in name:
        return {
            "kind": "likes",
            "label": "Link da Publicação",
            "placeholder": "Cole o link da publicação",
            "help": "Use o link do post que receberá as curtidas.",
        }
    if "visualiza" in name:
        return {
            "kind": "views",
            "label": "Link do Vídeo",
            "placeholder": "Cole o link do vídeo ou Reels",
            "help": "Use o link do vídeo que receberá as visualizações.",
        }
    return {
        "kind": "profile",
        "label": "Link ou @ do Perfil",
        "placeholder": "@usuario ou link do perfil",
        "help": "O perfil precisa estar público.",
    }


def _service_needs_custom_target(service):
    """Check if a service needs its own target link (not just the main order target)."""
    name = service.name.lower()
    return service.requires_comments or "curtida" in name or "visualiza" in name or "coment" in name


class OrderForm(forms.ModelForm):
    comments_text = forms.CharField(
        label="Comentários personalizados",
        max_length=20000,
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 7,
                "placeholder": "Escreva um comentário por linha",
                "maxlength": "20000",
            }
        ),
    )
    upsells = forms.ModelMultipleChoiceField(
        label="Serviços complementares",
        queryset=Package.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    confirm_public_profile = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.HiddenInput(),
    )
    accept_terms = forms.BooleanField(
        label="Li e concordo com os Termos de Uso.",
        required=True,
        error_messages={"required": "Você precisa aceitar os Termos de Uso."},
    )

    class Meta:
        model = Order
        fields = ("target", "comments_text", "whatsapp", "email")
        widgets = {
            "target": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "@usuario ou link", "maxlength": "500"}
            ),
            "whatsapp": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "(11) 99999-9999", "maxlength": "30"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "voce@email.com", "maxlength": "254"}
            ),
        }

    def __init__(self, *args, package, request=None, **kwargs):
        self.package = package
        self.request = request
        super().__init__(*args, **kwargs)
        self.target_config = target_field_config(package.service)
        self.fields["target"].label = self.target_config["label"]
        self.fields["target"].help_text = self.target_config["help"]
        self.fields["target"].widget.attrs["placeholder"] = self.target_config["placeholder"]
        self.fields["email"].required = settings.ORDER_EMAIL_REQUIRED or (
            not settings.PAYMENT_SIMULATED
            and settings.PAYMENT_PROVIDER == "mercadopago"
        )
        self.fields["email"].error_messages.update(
            {
                "required": "Informe um email válido para receber atualizações do pedido.",
                "invalid": "Informe um email válido para receber atualizações do pedido.",
            }
        )
        self.fields["comments_text"].required = package.service.requires_comments

        # Bonus options (optional, free)
        self.bonus_options = get_bonus_options_for_package(package)
        bonus_package_ids = {opt["package"].pk for opt in self.bonus_options}

        for idx, opt in enumerate(self.bonus_options):
            enabled_name = f"bonus_{idx}_enabled"
            target_name = f"bonus_{idx}_target"
            self.fields[enabled_name] = forms.BooleanField(
                required=False,
                label=f"Brinde: {opt['package'].formatted_quantity} {opt['package'].service.name}",
                widget=forms.CheckboxInput(attrs={
                    "class": "bonus-checkbox",
                    "data-kind": opt["kind"],
                    "data-idx": idx,
                    "data-label": f"{opt['package'].formatted_quantity} {opt['package'].service.name}",
                    "data-platform": opt["package"].service.platform.slug,
                    "data-price": str(opt["package"].price_brl),
                }),
            )
            self.fields[target_name] = forms.CharField(
                required=False,
                max_length=500,
                label=opt["label"],
                widget=forms.TextInput(attrs={
                    "class": "form-control bonus-target-input",
                    "placeholder": opt["placeholder"],
                    "data-idx": idx,
                    "maxlength": "500",
                }),
            )
            opt["enabled_field"] = self[enabled_name]
            opt["target_field"] = self[target_name]
            opt["idx"] = idx

        # Paid complements — exclude any package already offered as bonus
        complement_ids = [
            complement.pk
            for complement in get_checkout_complements(package)
            if complement.pk not in bonus_package_ids
        ]
        self.upsell_targets = {}
        self.fields["upsells"].queryset = (
            Package.objects.filter(pk__in=complement_ids)
            .select_related("service")
            .order_by("service__position", "service__name", "service_id")
        )
        self.fields["accept_terms"].widget.attrs["class"] = "form-check-input"
        self.fields["upsells"].widget.attrs["class"] = "upsell-input"

    def clean_target(self):
        target = self.cleaned_data["target"].strip()
        if not validate_target_for_service(self.package.service, self.cleaned_data["target"]):
            raise forms.ValidationError(
                "Formato inválido. Não use espaços. Informe apenas @usuario ou um link válido."
            )
        return normalize_target_for_service(self.package.service, target)

    def clean_whatsapp(self):
        whatsapp = re.sub(r"\D", "", self.cleaned_data["whatsapp"])
        if not 10 <= len(whatsapp) <= 15:
            raise forms.ValidationError("Informe um WhatsApp válido com DDD.")
        return whatsapp

    def clean_comments_text(self):
        if not self.package.service.requires_comments:
            return ""
        comments = [
            line.strip()
            for line in self.cleaned_data.get("comments_text", "").splitlines()
            if line.strip()
        ]
        if len(comments) != self.package.quantity:
            raise forms.ValidationError(
                f"Informe exatamente {self.package.quantity} comentário(s), um por linha."
            )
        return "\n".join(comments)

    def clean_upsells(self):
        upsells = self.cleaned_data["upsells"]
        if len(upsells) > 3:
            raise forms.ValidationError("Escolha no máximo três serviços complementares.")
        service_ids = [package.service_id for package in upsells]
        if len(service_ids) != len(set(service_ids)):
            raise forms.ValidationError("Escolha somente um pacote por serviço complementar.")
        for package in upsells:
            service = package.service
            if service.min_quantity is not None and package.quantity < service.min_quantity:
                raise forms.ValidationError(
                    f"O pacote de {service.name} está abaixo do mínimo permitido."
                )
            if service.max_quantity is not None and package.quantity > service.max_quantity:
                raise forms.ValidationError(
                    f"O pacote de {service.name} está acima do máximo permitido."
                )

            if _service_needs_custom_target(service):
                upsell_target_key = f"upsell_target_{package.pk}"
                upsell_target = self.data.get(upsell_target_key, "").strip()

                if not upsell_target:
                    raise forms.ValidationError(
                        f"Informe o link específico para {service.name}."
                    )

                if not validate_target_for_service(service, upsell_target):
                    service_name_lower = service.name.lower()
                    if "curtida" in service_name_lower:
                        raise forms.ValidationError(
                            f"Link inválido para {service.name}. "
                            "Cole o link completo da publicação (instagram.com/p/, reel/, etc)."
                        )
                    elif "visualiza" in service_name_lower:
                        raise forms.ValidationError(
                            f"Link inválido para {service.name}. "
                            "Cole o link completo do Reels (instagram.com/reel/ ou instagram.com/reels/)."
                        )
                    elif "coment" in service_name_lower:
                        raise forms.ValidationError(
                            f"Link inválido para {service.name}. "
                            "Cole o link completo da publicação (instagram.com/p/, reel/, etc)."
                        )
                    else:
                        raise forms.ValidationError(
                            f"Formato inválido para {service.name}."
                        )

        return upsells

    def clean(self):
        cleaned_data = super().clean()
        service = self.package.service
        if not service.provider_service_id:
            raise forms.ValidationError("Este pacote está temporariamente indisponível.")
        if service.min_quantity is not None and self.package.quantity < service.min_quantity:
            raise forms.ValidationError("A quantidade está abaixo do mínimo do serviço.")
        if service.max_quantity is not None and self.package.quantity > service.max_quantity:
            raise forms.ValidationError("A quantidade está acima do máximo do serviço.")

        # Validate optional bonus targets
        for idx, opt in enumerate(self.bonus_options):
            enabled = cleaned_data.get(f"bonus_{idx}_enabled")
            target = (cleaned_data.get(f"bonus_{idx}_target") or "").strip()
            if not enabled:
                continue
            if not target:
                self.add_error(
                    f"bonus_{idx}_target",
                    f"Informe o destino para o brinde de {opt['package'].service.name}.",
                )
            elif not validate_target_for_service(opt["package"].service, target):
                self.add_error(
                    f"bonus_{idx}_target",
                    f"Link/perfil inválido para o brinde de {opt['package'].service.name}.",
                )

        return cleaned_data

    def save(self, commit=True):
        order = super().save(commit=False)
        order.package = self.package
        order.prepare_values()
        order.target = normalize_target_for_service(self.package.service, order.target)

        bonus_package_ids = {opt["package"].pk for opt in self.bonus_options}
        upsells = [
            package
            for package in self.cleaned_data["upsells"]
            if package.pk not in bonus_package_ids
        ]
        active_bonus_prices = [
            opt["package"].price_brl
            for idx, opt in enumerate(self.bonus_options)
            if self.cleaned_data.get(f"bonus_{idx}_enabled")
        ]
        order.amount_brl = (
            self.package.price_brl
            + sum((package.price_brl for package in upsells), Decimal("0"))
            + sum(active_bonus_prices, Decimal("0"))
        )
        order.accepted_terms = self.cleaned_data["accept_terms"]
        order.accepted_terms_at = timezone.now()
        order.terms_version = TERMS_VERSION
        order.confirmed_public_profile = True

        order.profile_username = ""
        order.profile_picture_url = ""
        order.profile_is_public = None
        order.profile_checked_at = None

        if self.request:
            order.customer_ip = get_client_ip(self.request)
            order.customer_user_agent = self.request.META.get("HTTP_USER_AGENT", "")[:500]

        if commit:
            order.full_clean()
            order.save()

            # Main package + paid upsells
            for package in [self.package, *upsells]:
                item = OrderItem(order=order, package=package)
                item.prepare_values()
                item_target = order.target
                if package in upsells:
                    item_target = (
                        getattr(self, "upsell_targets", {}).get(package.id)
                        or self.data.get(f"upsell_target_{package.id}")
                        or order.target
                    )
                item.target = normalize_target_for_service(package.service, item_target)
                item.full_clean()
                item.save()

            # Optional free bonuses
            for idx, opt in enumerate(self.bonus_options):
                if not self.cleaned_data.get(f"bonus_{idx}_enabled"):
                    continue
                raw_target = (self.cleaned_data.get(f"bonus_{idx}_target") or "").strip()
                bonus_target = normalize_target_for_service(opt["package"].service, raw_target)
                bonus_item = OrderItem(order=order, package=opt["package"])
                bonus_item.prepare_values()
                bonus_item.target = bonus_target
                bonus_item.full_clean()
                bonus_item.save()

        return order


class OrderLookupForm(forms.Form):
    code = forms.CharField(
        label="Código do pedido",
        max_length=20,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Ex.: A1B2C3D4E5F6"}
        ),
    )
    contact = forms.CharField(
        label="WhatsApp ou email",
        max_length=254,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Contato usado na compra"}
        ),
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()
