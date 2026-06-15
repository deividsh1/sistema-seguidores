from django.urls import path

from store import views


app_name = "store"

urlpatterns = [
    path("", views.home, name="home"),
    path("servicos-digitais/", views.digital_services, name="digital_services"),
    path("como-fazer-um-pedido/", views.how_to_order, name="how_to_order"),
    path("instagram/", views.platform_detail, {"slug": "instagram"}, name="instagram"),
    path("tiktok/", views.platform_detail, {"slug": "tiktok"}, name="tiktok"),
    path("plataforma/<slug:slug>/", views.platform_detail, name="platform"),
    path("checkout/<int:package_id>/", views.checkout, name="checkout"),
    path("pagamento/<str:code>/", views.payment, name="payment"),
    path(
        "pagamento/<str:code>/verificar/",
        views.verify_payment,
        name="verify_payment",
    ),
    path("pedido/<str:code>/sucesso/", views.success, name="success"),
    path("pedido/consultar/", views.order_lookup, name="order_lookup"),
    path("api/profile-preview/", views.profile_preview, name="profile_preview"),
    path("api/profile-media/", views.profile_media, name="profile_media"),
    path("termos-de-uso/", views.terms, name="terms"),
    path(
        "webhooks/mercadopago/",
        views.mercadopago_webhook,
        name="mercadopago_webhook",
    ),
    path("webhooks/payment/", views.payment_webhook, name="payment_webhook"),
]
