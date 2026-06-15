from django.contrib import admin, messages

from store.models import (
    Order,
    OrderItem,
    Package,
    PaymentLog,
    Platform,
    ProviderLog,
    Service,
)
from store.services.order_processing import dispatch_paid_order
from store.services.provider_api import ProviderAPIError, get_order_status


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "position")
    list_editable = ("active", "position")
    prepopulated_fields = {"slug": ("name",)}


class PackageInline(admin.TabularInline):
    model = Package
    extra = 0
    fields = ("name", "quantity", "price_brl", "active", "featured", "position")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "platform",
        "provider_service_id",
        "min_quantity",
        "max_quantity",
        "requires_comments",
        "active",
        "position",
    )
    list_filter = ("platform", "active")
    list_editable = (
        "provider_service_id",
        "min_quantity",
        "max_quantity",
        "requires_comments",
        "active",
        "position",
    )
    search_fields = ("name", "provider_service_id")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (PackageInline,)


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("name", "service", "quantity", "price_brl", "featured", "active")
    list_filter = ("service__platform", "service", "active", "featured")
    list_editable = ("quantity", "price_brl", "featured", "active")
    search_fields = ("name", "service__name")


class PaymentLogInline(admin.TabularInline):
    model = PaymentLog
    extra = 0
    can_delete = False
    readonly_fields = (
        "event_type",
        "external_payment_id",
        "status",
        "amount",
        "signature_valid",
        "created_at",
    )
    exclude = ("pix_code", "qr_code_base64", "response_data", "payment_url")

    def has_add_permission(self, request, obj=None):
        return False


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = tuple(field.name for field in OrderItem._meta.fields)

    def has_add_permission(self, request, obj=None):
        return False


@admin.action(description="Reprocessar pedidos pagos")
def retry_processing(modeladmin, request, queryset):
    processed = sum(dispatch_paid_order(order.id, retry_errors=True) for order in queryset)
    modeladmin.message_user(
        request, f"{processed} pedido(s) processado(s).", messages.SUCCESS
    )


@admin.action(description="Atualizar status externo")
def refresh_external_status(modeladmin, request, queryset):
    updated = 0
    for order in queryset:
        for item in order.items.exclude(external_order_id="").exclude(
            external_order_id__startswith="SIM-"
        ):
            try:
                data = get_order_status(item.external_order_id)
            except ProviderAPIError:
                continue
            item.external_status = str(data.get("status", ""))
            item.save(update_fields=("external_status",))
            updated += 1
        first_item = order.items.first()
        if first_item:
            order.provider_status = first_item.external_status
            order.save(update_fields=("provider_status", "updated_at"))
    modeladmin.message_user(request, f"{updated} status atualizado(s).", messages.SUCCESS)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "platform_name",
        "service_name",
        "quantity",
        "amount_brl",
        "payment_status",
        "fulfillment_status",
        "created_at",
    )
    list_filter = (
        "payment_status",
        "fulfillment_status",
        "package__service__platform",
    )
    search_fields = ("code", "whatsapp", "email", "target", "external_order_id")
    readonly_fields = tuple(field.name for field in Order._meta.fields)
    actions = (retry_processing, refresh_external_status)
    inlines = (OrderItemInline, PaymentLogInline)

    def has_add_permission(self, request):
        return False


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "event_type",
        "order",
        "status",
        "amount",
        "signature_valid",
    )
    list_filter = ("event_type", "status", "signature_valid")
    search_fields = ("order__code", "external_payment_id")
    readonly_fields = tuple(field.name for field in PaymentLog._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(ProviderLog)
class ProviderLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "level", "action", "order", "message")
    list_filter = ("level", "action")
    search_fields = ("order__code", "message")
    readonly_fields = tuple(field.name for field in ProviderLog._meta.fields)

    def has_add_permission(self, request):
        return False


admin.site.site_header = "WebMaster | Administração"
admin.site.site_title = "WebMaster"
admin.site.index_title = "Gestão da loja"
