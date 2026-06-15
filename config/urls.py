from django.contrib import admin
from django.views.generic import RedirectView
from django.urls import include, path


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url='/static/img/webmaster-logo.webp', permanent=True)),
    path("admin/", admin.site.urls),
    path("", include("store.urls")),
]
