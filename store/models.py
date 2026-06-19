import secrets
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


TERMS_VERSION = "2026-06-09"


def generate_order_code():
    return secrets.token_hex(10).upper()


class Platform(models.Model):
    name = models.CharField("nome", max_length=80, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField("descrição", blank=True)
    active = models.BooleanField("ativa", default=True)
    position = models.PositiveIntegerField("posição", default=0)

    class Meta:
        verbose_name = "plataforma"
        verbose_name_plural = "plataformas"
        ordering = ("position", "name")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:platform", kwargs={"slug": self.slug})


class Service(models.Model):
    platform = models.ForeignKey(
        Platform,
        verbose_name="plataforma",
        related_name="services",
        on_delete=models.PROTECT,
    )
    name = models.CharField("nome", max_length=120)
    slug = models.SlugField(blank=True)
    description = models.TextField("descrição", blank=True)
    provider_service_id = models.CharField(
        "provider_service_id",
        max_length=100,
        blank=True,
        help_text="ID técnico do serviço configurado na integração externa.",
    )
    min_quantity = models.PositiveIntegerField(
        "quantidade mínima",
        null=True,
        blank=True,
        help_text="Limite opcional informado pela integração de entrega.",
    )
    max_quantity = models.PositiveIntegerField(
        "quantidade máxima",
        null=True,
        blank=True,
        help_text="Limite opcional informado pela integração de entrega.",
    )
    requires_comments = models.BooleanField(
        "exige comentários personalizados",
        default=False,
        help_text="Solicita um comentário por linha no checkout.",
    )
    active = models.BooleanField("ativo", default=True)
    position = models.PositiveIntegerField("posição", default=0)

    class Meta:
        verbose_name = "serviço"
        verbose_name_plural = "serviços"
        ordering = ("position", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("platform", "slug"), name="unique_service_slug_per_platform"
            )
        ]

    def __str__(self):
        return f"{self.platform} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def clean(self):
        if self.active and not self.provider_service_id:
            raise ValidationError(
                {"provider_service_id": "Informe o ID técnico antes de ativar o serviço."}
            )
        if (
            self.min_quantity is not None
            and self.max_quantity is not None
            and self.min_quantity > self.max_quantity
        ):
            raise ValidationError(
                {"max_quantity": "A quantidade máxima deve ser maior ou igual à mínima."}
            )


class Package(models.Model):
    service = models.ForeignKey(
        Service,
        verbose_name="serviço",
        related_name="packages",
        on_delete=models.PROTECT,
    )
    name = models.CharField("nome do pacote", max_length=120)
    quantity = models.PositiveIntegerField(
        "quantidade", help_text="Quantidade enviada para a integração externa."
    )
    price_brl = models.DecimalField(
        "preço em reais",
        max_digits=12,
        decimal_places=2,
        help_text="Preço final manual cobrado do cliente.",
    )
    active = models.BooleanField("ativo", default=True)
    featured = models.BooleanField("destaque", default=False)
    position = models.PositiveIntegerField("posição", default=0)

    class Meta:
        verbose_name = "pacote"
        verbose_name_plural = "pacotes"
        ordering = ("position", "quantity")
        constraints = [
            models.UniqueConstraint(
                fields=("service", "quantity"), name="unique_package_quantity_per_service"
            )
        ]

    def __str__(self):
        return f"{self.service} - {self.name}"

    @property
    def formatted_quantity(self):
        return f"{self.quantity:,}".replace(",", ".")

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({"quantity": "A quantidade deve ser maior que zero."})
        if self.active and self.price_brl <= Decimal("0"):
            raise ValidationError(
                {"price_brl": "Defina um preço maior que zero antes de ativar o pacote."}
            )
        if self.price_brl < Decimal("0"):
            raise ValidationError({"price_brl": "O preço não pode ser negativo."})
        if self.service_id:
            if (
                self.service.min_quantity is not None
                and self.quantity < self.service.min_quantity
            ):
                raise ValidationError(
                    {"quantity": "A quantidade está abaixo do mínimo do serviço."}
                )
            if (
                self.service.max_quantity is not None
                and self.quantity > self.service.max_quantity
            ):
                raise ValidationError(
                    {"quantity": "A quantidade está acima do máximo do serviço."}
                )

    def get_absolute_url(self):
        return reverse("store:checkout", kwargs={"package_id": self.pk})


class Order(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Aguardando pagamento"
        PAID = "paid", "Pago"
        REJECTED = "rejected", "Rejeitado"
        CANCELLED = "cancelled", "Cancelado"
        REFUNDED = "refunded", "Reembolsado"
        ERROR = "error", "Erro"

    class FulfillmentStatus(models.TextChoices):
        PENDING = "pending", "Aguardando pagamento"
        SUBMITTING = "submitting", "Processando"
        SUBMITTED = "submitted", "Pedido enviado"
        ERROR = "error", "Erro no processamento"

    code = models.CharField(
        "código", max_length=20, unique=True, default=generate_order_code, editable=False
    )
    package = models.ForeignKey(
        Package, verbose_name="pacote", related_name="orders", on_delete=models.PROTECT
    )
    platform_name = models.CharField("plataforma", max_length=80)
    service_name = models.CharField("serviço", max_length=120)
    package_name = models.CharField("pacote", max_length=120)
    provider_service_id = models.CharField(
        "provider_service_id", max_length=100, editable=False
    )
    target = models.CharField("link ou @perfil", max_length=500)
    comments_text = models.TextField(
        "comentários personalizados", max_length=20000, blank=True
    )
    quantity = models.PositiveIntegerField("quantidade")
    amount_brl = models.DecimalField("total", max_digits=12, decimal_places=2)
    whatsapp = models.CharField("WhatsApp", max_length=30)
    email = models.EmailField("email", blank=True)

    accepted_terms = models.BooleanField("aceitou os termos", default=False)
    accepted_terms_at = models.DateTimeField("aceite registrado em", null=True, blank=True)
    terms_version = models.CharField("versão dos termos", max_length=30, blank=True)
    confirmed_public_profile = models.BooleanField(
        "confirmou perfil público", default=False
    )
    profile_username = models.CharField("usuário do perfil", max_length=160, blank=True)
    profile_picture_url = models.URLField(
        "foto do perfil", max_length=1000, blank=True
    )
    profile_is_public = models.BooleanField(
        "perfil público", null=True, blank=True
    )
    profile_checked_at = models.DateTimeField(
        "perfil verificado em", null=True, blank=True
    )
    customer_ip = models.GenericIPAddressField("IP do cliente", null=True, blank=True)
    customer_user_agent = models.CharField("user agent", max_length=500, blank=True)
    fb_fbp = models.CharField("Meta _fbp", max_length=255, blank=True)
    fb_fbc = models.CharField("Meta _fbc", max_length=255, blank=True)

    payment_status = models.CharField(
        "status do pagamento",
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    external_payment_id = models.CharField(
        "ID externo do pagamento", max_length=120, blank=True, db_index=True
    )
    fulfillment_status = models.CharField(
        "status do pedido",
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.PENDING,
    )
    external_order_id = models.CharField(
        "ID externo do pedido", max_length=100, blank=True
    )
    provider_status = models.CharField("status externo", max_length=100, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)
    paid_at = models.DateTimeField("pago em", null=True, blank=True)
    submitted_at = models.DateTimeField("enviado em", null=True, blank=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("code",)),
            models.Index(fields=("payment_status", "fulfillment_status")),
        ]

    def __str__(self):
        return f"Pedido {self.code}"

    def clean(self):
        if self.package_id and self.quantity != self.package.quantity:
            raise ValidationError({"quantity": "A quantidade deve corresponder ao pacote."})
        if self.package_id and self.amount_brl < self.package.price_brl:
            raise ValidationError(
                {"amount_brl": "O valor não pode ser menor que o pacote principal."}
            )
        if self.package_id:
            if not self.provider_service_id:
                raise ValidationError(
                    {"provider_service_id": "O pedido precisa de um ID técnico de serviço."}
                )
            if not self.accepted_terms or not self.accepted_terms_at:
                raise ValidationError({"accepted_terms": "O aceite dos termos é obrigatório."})
            if not self.confirmed_public_profile:
                raise ValidationError(
                    {"confirmed_public_profile": "Confirme que o perfil está público."}
                )
            if self.package.service.requires_comments:
                comments = [
                    line.strip() for line in self.comments_text.splitlines() if line.strip()
                ]
                if len(comments) != self.quantity:
                    raise ValidationError(
                        {
                            "comments_text": (
                                f"Informe exatamente {self.quantity} comentário(s), "
                                "um por linha."
                            )
                        }
                    )

    def prepare_values(self):
        service = self.package.service
        self.platform_name = service.platform.name
        self.service_name = service.name
        self.package_name = self.package.name
        self.provider_service_id = service.provider_service_id
        self.quantity = self.package.quantity
        self.amount_brl = self.package.price_brl

    def mark_paid(self):
        self.payment_status = self.PaymentStatus.PAID
        self.paid_at = self.paid_at or timezone.now()

    def get_absolute_url(self):
        return reverse("store:payment", kwargs={"code": self.code})


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, verbose_name="pedido", related_name="items", on_delete=models.CASCADE
    )
    package = models.ForeignKey(
        Package, verbose_name="pacote", related_name="order_items", on_delete=models.PROTECT
    )
    service_name = models.CharField("serviço", max_length=120)
    package_name = models.CharField("pacote", max_length=120)
    provider_service_id = models.CharField(
        "provider_service_id", max_length=100, editable=False
    )
    target = models.CharField("link ou @perfil", max_length=500)
    comments_text = models.TextField(
        "comentários personalizados", max_length=20000, blank=True
    )
    quantity = models.PositiveIntegerField("quantidade")
    total_amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    fulfillment_status = models.CharField(
        "status",
        max_length=20,
        choices=Order.FulfillmentStatus.choices,
        default=Order.FulfillmentStatus.PENDING,
    )
    external_order_id = models.CharField("ID externo", max_length=100, blank=True)
    external_status = models.CharField("status externo", max_length=100, blank=True)
    submitted_at = models.DateTimeField("enviado em", null=True, blank=True)

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("order", "package"), name="unique_package_per_order"
            )
        ]

    def __str__(self):
        return f"{self.order.code} - {self.service_name}"

    def prepare_values(self):
        self.service_name = self.package.service.name
        self.package_name = self.package.name
        self.provider_service_id = self.package.service.provider_service_id
        self.quantity = self.package.quantity
        self.total_amount = self.package.price_brl
        self.target = self.order.target
        self.comments_text = (
            self.order.comments_text if self.package.service.requires_comments else ""
        )


class PaymentLog(models.Model):
    class EventType(models.TextChoices):
        CHARGE = "charge", "Cobrança criada"
        WEBHOOK = "webhook", "Webhook recebido"
        STATUS = "status", "Status consultado"
        ERROR = "error", "Erro"

    order = models.ForeignKey(
        Order,
        verbose_name="pedido",
        related_name="payment_logs",
        on_delete=models.CASCADE,
    )
    event_type = models.CharField(
        "evento", max_length=20, choices=EventType.choices
    )
    external_payment_id = models.CharField(
        "ID externo do pagamento", max_length=120, blank=True, db_index=True
    )
    status = models.CharField("status", max_length=50, blank=True)
    amount = models.DecimalField(
        "valor", max_digits=12, decimal_places=2, null=True, blank=True
    )
    pix_code = models.TextField("Pix copia e cola", blank=True)
    qr_code_base64 = models.TextField("QR Code em base64", blank=True)
    payment_url = models.URLField("link do pagamento", max_length=1000, blank=True)
    signature_valid = models.BooleanField("assinatura válida", default=False)
    response_data = models.JSONField("resposta sanitizada", default=dict, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "log de pagamento"
        verbose_name_plural = "logs de pagamento"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.order.code}"


class ProviderLog(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Informação"
        ERROR = "error", "Erro"

    order = models.ForeignKey(
        Order,
        verbose_name="pedido",
        related_name="provider_logs",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    level = models.CharField(
        "nível", max_length=10, choices=Level.choices, default=Level.INFO
    )
    action = models.CharField("ação", max_length=100)
    message = models.TextField("mensagem")
    response_data = models.JSONField("resposta sanitizada", default=dict, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "log de integração"
        verbose_name_plural = "logs de integração"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.get_level_display()}: {self.action}"
