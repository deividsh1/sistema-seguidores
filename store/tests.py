import hashlib
import hmac
import json
import re
import time
from collections import Counter
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from store.models import (
    Order,
    OrderItem,
    Package,
    PaymentLog,
    Platform,
    ProviderLog,
    Service,
)
from store.services.catalog import get_bonus_packages_for_package, get_checkout_complements
from store.services.order_processing import dispatch_paid_order, process_payment_notification
from store.services.payment_api import PaymentAPIError, create_pix_charge, get_payment_status
from store.services.provider_api import (
    ProviderAPIError,
    cancel_orders,
    create_multiple_refill,
    create_refill,
    get_balance,
    get_multiple_order_status,
    get_multiple_refill_status,
    get_order_status,
    get_refill_status,
    list_services,
    submit_order,
)


@override_settings(
    PAYMENT_SIMULATED=True,
    PROVIDER_SIMULATED=True,
    PAYMENT_WEBHOOK_SECRET="test-webhook-secret",
)
class StoreFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.platform = Platform.objects.create(name="Instagram", slug="instagram")
        self.service = Service.objects.create(
            platform=self.platform,
            name="Seguidores",
            slug="seguidores",
            provider_service_id="9142",
        )
        self.package = Package.objects.create(
            service=self.service,
            name="500",
            quantity=500,
            price_brl=Decimal("29.90"),
        )
        self.upsell_service = Service.objects.create(
            platform=self.platform,
            name="Curtidas",
            slug="curtidas",
            provider_service_id="10635",
        )
        self.upsell_package = Package.objects.create(
            service=self.upsell_service,
            name="500",
            quantity=500,
            price_brl=Decimal("14.90"),
        )
        self.second_upsell_package = Package.objects.create(
            service=self.upsell_service,
            name="1000",
            quantity=1000,
            price_brl=Decimal("24.90"),
        )
        self.comments_service = Service.objects.create(
            platform=self.platform,
            name="Comentários Personalizados Instagram",
            slug="comentarios-personalizados-instagram",
            provider_service_id="1723",
            requires_comments=True,
        )
        self.comments_package = Package.objects.create(
            service=self.comments_service,
            name="5 Comentários Personalizados",
            quantity=5,
            price_brl=Decimal("5.90"),
        )

    def checkout_order(self, with_upsell=False):
        data = {
            "target": "@cliente.teste",
            "whatsapp": "(11) 99999-9999",
            "email": "cliente@example.com",
            "confirm_public_profile": "on",
            "accept_terms": "on",
        }
        if with_upsell:
            data["upsells"] = [str(self.upsell_package.id)]
            data[f"upsell_target_{self.upsell_package.id}"] = "https://www.instagram.com/p/ABC123/"
        response = self.client.post(
            self.package.get_absolute_url(),
            data,
            HTTP_USER_AGENT="Test Browser",
        )
        order = Order.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("store:payment", args=[order.code]))
        return order

    def post_checkout_target(self, package, target):
        data = {
            "target": target,
            "whatsapp": "11999999999",
            "email": "cliente@example.com",
            "confirm_public_profile": "on",
            "accept_terms": "on",
        }
        data.update(self.bonus_target_data(package))
        return self.client.post(
            package.get_absolute_url(),
            data,
        )

    def bonus_target_data(self, package):
        targets = {}
        for bonus in get_bonus_packages_for_package(package):
            name = bonus.service.name.lower()
            if "visualiza" in name:
                target = "https://www.instagram.com/reel/BRINDEVIEWS/"
            elif "curtida" in name or "coment" in name:
                target = "https://www.instagram.com/p/BRINDELIKES/"
            else:
                target = "@brinde.perfil"
            targets[f"bonus_target_{bonus.id}"] = target
        return targets

    def create_views_catalog(self):
        service = Service.objects.create(
            platform=self.platform,
            name="Visualizações Instagram Reels",
            slug="visualizacoes-reels",
            provider_service_id="8061",
        )
        packages = {}
        for position, (quantity, price) in enumerate((
            (3000, "6.18"),
            (5000, "10.00"),
            (10000, "14.00"),
            (20000, "25.00"),
            (50000, "35.90"),
        ), start=1):
            packages[quantity] = Package.objects.create(
                service=service,
                name=f"{quantity} Visualizações",
                quantity=quantity,
                price_brl=Decimal(price),
                position=position,
            )
        return packages

    def test_followers_do_not_receive_incompatible_automatic_bonus(self):
        follower_packages = [
            self.package,
            Package.objects.create(
                service=self.service,
                name="2000",
                quantity=2000,
                price_brl=Decimal("69.90"),
            ),
            Package.objects.create(
                service=self.service,
                name="10000",
                quantity=10000,
                price_brl=Decimal("199.90"),
            ),
        ]
        self.create_views_catalog()

        for package in follower_packages:
            self.assertEqual(get_bonus_packages_for_package(package), [])

    def test_compatible_bonus_improves_with_likes_package(self):
        views = self.create_views_catalog()
        likes_5000 = Package.objects.create(
            service=self.upsell_service,
            name="5000",
            quantity=5000,
            price_brl=Decimal("39.90"),
        )

        self.assertEqual(
            get_bonus_packages_for_package(self.upsell_package),
            [self.package, views[3000]],
        )
        self.assertEqual(
            get_bonus_packages_for_package(self.second_upsell_package),
            [self.package, views[5000]],
        )
        self.assertEqual(
            get_bonus_packages_for_package(likes_5000),
            [self.package, views[10000]],
        )

    def test_large_views_packages_receive_compatible_likes_bonus(self):
        views = self.create_views_catalog()
        Package.objects.create(
            service=self.upsell_service,
            name="250",
            quantity=250,
            price_brl=Decimal("4.90"),
        )

        self.assertEqual(
            get_bonus_packages_for_package(views[10000]),
            [self.second_upsell_package, self.package],
        )
        self.assertEqual(
            get_bonus_packages_for_package(views[50000]),
            [self.second_upsell_package, self.package],
        )

    def test_bonus_is_shown_and_saved_at_zero_without_changing_total(self):
        views = self.create_views_catalog()
        response = self.client.get(self.upsell_package.get_absolute_url())
        self.assertContains(response, "Brindes inclusos")
        self.assertContains(response, "500 Seguidores")
        self.assertContains(response, "Brinde: 3.000 Visualizações Instagram Reels")
        self.assertContains(response, "R$ 0,00")

        data = {
            "target": "https://www.instagram.com/p/publicacao/",
            "whatsapp": "11999999999",
            "email": "cliente@example.com",
            "accept_terms": "on",
        }
        data.update(self.bonus_target_data(self.upsell_package))
        response = self.client.post(
            self.upsell_package.get_absolute_url(),
            data,
        )
        order = Order.objects.get()
        self.assertRedirects(response, reverse("store:payment", args=[order.code]))
        self.assertEqual(order.amount_brl, self.upsell_package.price_brl)
        self.assertEqual(order.items.count(), 3)

        follower_bonus = order.items.get(package=self.package)
        views_bonus = order.items.get(package=views[3000])
        for bonus_item in (follower_bonus, views_bonus):
            self.assertEqual(bonus_item.total_amount, Decimal("0"))
            self.assertTrue(bonus_item.package_name.startswith("Brinde: "))
        self.assertEqual(
            follower_bonus.target,
            "https://www.instagram.com/brinde.perfil/",
        )
        self.assertEqual(
            views_bonus.target,
            "https://www.instagram.com/reel/BRINDEVIEWS/",
        )
        self.assertNotEqual(follower_bonus.target, order.target)
        self.assertNotEqual(views_bonus.target, order.target)

    def test_bonus_targets_are_required_validated_and_preserved(self):
        views = self.create_views_catalog()
        response = self.client.post(
            self.upsell_package.get_absolute_url(),
            {
                "target": "https://www.instagram.com/p/publicacao/",
                "whatsapp": "11999999999",
                "email": "cliente@example.com",
                "accept_terms": "on",
                f"bonus_target_{self.package.id}": "@brinde.perfil",
                f"bonus_target_{views[3000].id}": "@destino-invalido",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f"bonus_target_{views[3000].id}",
            response.context["form"].errors,
        )
        self.assertContains(response, "@destino-invalido")
        self.assertContains(response, "Use link de vídeo/Reels")
        self.assertFalse(Order.objects.exists())

    def test_bonus_is_not_duplicated_as_paid_upsell(self):
        views = self.create_views_catalog()
        response = self.client.get(self.upsell_package.get_absolute_url())
        upsell_queryset = response.context["form"].fields["upsells"].queryset
        self.assertNotIn(views[3000], upsell_queryset)
        self.assertEqual(list(upsell_queryset), [])

    def test_switching_package_recalculates_bonus_on_server(self):
        views = self.create_views_catalog()

        small_checkout = self.client.get(self.upsell_package.get_absolute_url())
        larger_checkout = self.client.get(self.second_upsell_package.get_absolute_url())

        self.assertEqual(
            small_checkout.context["bonus_packages"],
            [self.package, views[3000]],
        )
        self.assertEqual(
            larger_checkout.context["bonus_packages"],
            [self.package, views[5000]],
        )

    def test_checkout_complements_follow_selected_package_level(self):
        self.package.position = 1
        self.package.save(update_fields=("position",))
        follower_packages = {
            500: self.package,
            1000: Package.objects.create(
                service=self.service,
                name="1000",
                quantity=1000,
                price_brl=Decimal("49.90"),
                position=2,
            ),
            2000: Package.objects.create(
                service=self.service,
                name="2000",
                quantity=2000,
                price_brl=Decimal("79.90"),
                position=3,
            ),
            3000: Package.objects.create(
                service=self.service,
                name="3000",
                quantity=3000,
                price_brl=Decimal("99.90"),
                position=4,
            ),
        }
        likes_250 = Package.objects.create(
            service=self.upsell_service,
            name="250",
            quantity=250,
            price_brl=Decimal("4.90"),
            position=1,
        )
        self.upsell_package.position = 2
        self.upsell_package.save(update_fields=("position",))
        self.second_upsell_package.position = 3
        self.second_upsell_package.save(update_fields=("position",))
        likes_2200 = Package.objects.create(
            service=self.upsell_service,
            name="2200",
            quantity=2200,
            price_brl=Decimal("18.99"),
            position=4,
        )
        views = self.create_views_catalog()
        expected = {
            500: {self.upsell_service.id: likes_250.id, views[3000].service_id: views[3000].id},
            1000: {self.upsell_service.id: self.upsell_package.id, views[5000].service_id: views[5000].id},
            2000: {self.upsell_service.id: self.second_upsell_package.id, views[10000].service_id: views[10000].id},
            3000: {self.upsell_service.id: likes_2200.id, views[20000].service_id: views[20000].id},
        }

        for quantity, selected_package in follower_packages.items():
            complements = get_checkout_complements(selected_package)
            self.assertEqual(
                {package.service_id: package.id for package in complements},
                expected[quantity],
            )
            response = self.client.get(selected_package.get_absolute_url())
            self.assertEqual(
                {
                    package.service_id: package.id
                    for package in response.context["form"].fields["upsells"].queryset
                },
                expected[quantity],
            )

    def test_checkout_complement_uses_closest_lower_level_and_creates_items(self):
        self.package.position = 4
        self.package.save(update_fields=("position",))
        Package.objects.create(
            service=self.service,
            name="1000",
            quantity=1000,
            price_brl=Decimal("49.90"),
            position=1,
        )
        Package.objects.create(
            service=self.service,
            name="2000",
            quantity=2000,
            price_brl=Decimal("79.90"),
            position=2,
        )
        Package.objects.create(
            service=self.service,
            name="3000",
            quantity=3000,
            price_brl=Decimal("99.90"),
            position=3,
        )
        self.upsell_package.position = 1
        self.upsell_package.save(update_fields=("position",))
        self.second_upsell_package.position = 2
        self.second_upsell_package.save(update_fields=("position",))
        views = self.create_views_catalog()

        complements = get_checkout_complements(self.package)
        self.assertEqual(
            {package.service_id: package.quantity for package in complements},
            {self.upsell_service.id: 1000, views[20000].service_id: 20000},
        )
        response = self.client.post(
            self.package.get_absolute_url(),
            {
                "target": "@cliente.teste",
                "whatsapp": "11999999999",
                "email": "cliente@example.com",
                "accept_terms": "on",
                "upsells": [str(package.id) for package in complements],
                f"upsell_target_{self.second_upsell_package.id}": "https://www.instagram.com/p/ABC123/",
                f"upsell_target_{views[20000].id}": "https://www.instagram.com/reel/XYZ789/",
            },
        )
        order = Order.objects.get()
        self.assertRedirects(response, reverse("store:payment", args=[order.code]))
        self.assertEqual(
            order.amount_brl,
            self.package.price_brl + self.second_upsell_package.price_brl + views[20000].price_brl,
        )
        self.assertEqual(order.items.count(), 3)

    def test_checkout_copies_package_and_technical_id(self):
        order = self.checkout_order()
        self.assertEqual(order.provider_service_id, "9142")
        self.assertEqual(order.quantity, 500)
        self.assertEqual(order.amount_brl, Decimal("29.90"))
        self.assertTrue(order.accepted_terms)
        self.assertTrue(order.confirmed_public_profile)
        self.assertEqual(order.terms_version, "2026-06-09")
        self.assertEqual(order.customer_user_agent, "Test Browser")
        self.assertEqual(order.items.count(), 1)
        charge = order.payment_logs.get(event_type="charge")
        self.assertEqual(order.external_payment_id, charge.external_payment_id)

    def test_checkout_calculates_upsells_server_side(self):
        order = self.checkout_order(with_upsell=True)
        self.assertEqual(order.amount_brl, Decimal("44.80"))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(
            set(order.items.values_list("provider_service_id", flat=True)),
            {"9142", "10635"},
        )
    

    def test_custom_comments_are_not_offered_as_upsell(self):
        response = self.client.get(self.package.get_absolute_url())
        self.assertNotContains(response, self.comments_package.name)
        self.assertContains(response, 'name="upsells"', count=1)

    def test_checkout_only_offers_relevant_active_upsells(self):
        views_service = Service.objects.create(
            platform=self.platform,
            name="Visualizações Instagram Reels",
            slug="visualizacoes-reels",
            provider_service_id="8061",
        )
        views_package = Package.objects.create(
            service=views_service,
            name="3.000 Visualizações",
            quantity=3000,
            price_brl=Decimal("6.18"),
        )
        response = self.client.get(self.upsell_package.get_absolute_url())
        upsells = list(response.context["form"].fields["upsells"].queryset)
        self.assertEqual(upsells, [])
        self.assertContains(response, views_package.name)
        self.assertContains(response, self.package.service.name)
        self.assertNotContains(response, self.comments_package.name)

    def test_custom_comments_field_is_conditional_and_validated(self):
        response = self.client.get(self.package.get_absolute_url())
        self.assertNotContains(response, 'name="comments_text"')
        response = self.client.get(self.comments_package.get_absolute_url())
        self.assertContains(response, 'name="comments_text"')

        response = self.client.post(
            self.comments_package.get_absolute_url(),
            {
                "target": "https://www.instagram.com/p/publicacao/",
                "comments_text": "Um\nDois",
                "whatsapp": "11999999999",
                "confirm_public_profile": "on",
                "accept_terms": "on",
            },
        )
        self.assertContains(response, "exatamente 5 comentário(s)")
        self.assertFalse(Order.objects.exists())

    def test_custom_comments_are_saved_on_order_and_item(self):
        comments = "Primeiro\nSegundo\nTerceiro\nQuarto\nQuinto"
        response = self.client.post(
            self.comments_package.get_absolute_url(),
            {
                "target": "https://www.instagram.com/reel/publicacao/",
                "comments_text": comments,
                "whatsapp": "11999999999",
                "email": "cliente@example.com",
                "confirm_public_profile": "on",
                "accept_terms": "on",
            },
        )
        order = Order.objects.get()
        self.assertRedirects(response, reverse("store:payment", args=[order.code]))
        self.assertEqual(order.comments_text, comments)
        self.assertEqual(order.items.get().comments_text, comments)

    def test_custom_comments_require_photo_or_video_link(self):
        response = self.client.post(
            self.comments_package.get_absolute_url(),
            {
                "target": "@cliente.teste",
                "comments_text": "Um\nDois\nTrês\nQuatro\nCinco",
                "whatsapp": "11999999999",
                "confirm_public_profile": "on",
                "accept_terms": "on",
            },
        )
        self.assertContains(response, "Formato inválido")
        self.assertFalse(Order.objects.exists())

    def test_checkout_rejects_unoffered_upsell_package(self):
        response = self.client.post(
            self.package.get_absolute_url(),
            {
                "target": "@cliente.teste",
                "whatsapp": "11999999999",
                "email": "cliente@example.com",
                "confirm_public_profile": "on",
                "accept_terms": "on",
                "upsells": [
                    str(self.upsell_package.id),
                    str(self.second_upsell_package.id),
                ],
            },
        )
        self.assertContains(response, "não é uma das escolhas disponíveis")
        self.assertFalse(Order.objects.exists())

    def test_platform_page_has_anchor_navigation_and_dark_catalog(self):
        response = self.client.get(reverse("store:instagram"))
        self.assertContains(response, 'href="#seguidores"')
        self.assertContains(response, 'class="service-block"')
        self.assertContains(response, 'class="package-selector"')
        self.assertContains(response, "Escolher pacote")
        self.assertNotContains(response, 'class="package-scroll"')

    @override_settings(
        WHATSAPP_SUPPORT_NUMBER="+5518996650268",
        SOCIAL_PROOF_ENABLED=True,
    )
    def test_commercial_components_use_configured_support_and_generic_messages(self):
        response = self.client.get(reverse("store:home"))
        self.assertContains(response, "https://wa.me/5518996650268")
        self.assertContains(response, 'id="activity-toast"')
        self.assertContains(response, "Compras recentes")
        self.assertContains(response, "img/webmaster-logo.webp")
        self.assertContains(response, 'class="site-logo" width="64" height="64"')
        self.assertContains(response, 'class="whatsapp-float-img" width="62" height="62"')

    @override_settings(SOCIAL_PROOF_ENABLED=False)
    def test_social_proof_can_be_disabled(self):
        response = self.client.get(reverse("store:home"))
        self.assertNotContains(response, 'id="activity-toast"')

    def test_ad_safe_landing_uses_neutral_language(self):
        response = self.client.get(reverse("store:digital_services"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Serviços digitais para")
        self.assertContains(response, "incremento de métricas")
        self.assertContains(response, "Pedido rastreável")
        for aggressive_claim in (
            "ganhe fama instantânea",
            "viralize garantido",
            "engane algoritmo",
            "seguidores reais garantidos",
        ):
            self.assertNotContains(response, aggressive_claim)

    @override_settings(WHATSAPP_SUPPORT_NUMBER="+5518996650268")
    def test_success_support_link_includes_order_code(self):
        order = self.checkout_order()
        response = self.client.get(reverse("store:success", args=[order.code]))
        self.assertContains(response, "https://wa.me/5518996650268")
        self.assertContains(response, order.code)
        self.assertContains(response, "Falar com suporte")

    def test_terms_page_exists_and_checkout_links_to_it(self):
        response = self.client.get(reverse("store:terms"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TERMOS DE USO")
        checkout = self.client.get(self.package.get_absolute_url())
        self.assertContains(checkout, reverse("store:terms"))

    def test_how_to_order_page_and_checkout_link_exist(self):
        response = self.client.get(reverse("store:how_to_order"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Como fazer um pedido na")
        self.assertContains(response, "Escolha o serviço e o pacote")
        self.assertContains(response, "A WebMaster não solicita senha")
        self.assertContains(response, reverse("store:instagram"))
        self.assertContains(response, reverse("store:tiktok"))
        self.assertContains(response, reverse("store:order_lookup"))

        checkout = self.client.get(self.package.get_absolute_url())
        self.assertContains(checkout, reverse("store:how_to_order"))

    def test_featured_checkout_offer_badge_has_dedicated_class(self):
        self.package.featured = True
        self.package.save(update_fields=("featured",))
        response = self.client.get(self.package.get_absolute_url())
        self.assertContains(response, 'class="summary-offer-badge"')

    def test_checkout_has_single_target_and_profile_warning(self):
        response = self.client.get(self.package.get_absolute_url())
        self.assertEqual(response.content.count(b'id="id_target"'), 1)
        self.assertEqual(response.content.count(b'id="profile-warning"'), 1)
        ids = re.findall(r'id="([^"]+)"', response.content.decode())
        self.assertEqual([value for value, count in Counter(ids).items() if count > 1], [])

    def test_checkout_rejects_package_without_technical_id(self):
        service = Service.objects.create(
            platform=self.platform,
            name="Indisponível",
            slug="indisponivel",
            provider_service_id="",
        )
        package = Package.objects.create(
            service=service,
            name="100",
            quantity=100,
            price_brl=Decimal("10.00"),
        )
        response = self.client.get(package.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_checkout_validates_configured_quantity_limits(self):
        self.service.min_quantity = 600
        self.service.max_quantity = 1000
        self.service.save(update_fields=("min_quantity", "max_quantity"))
        response = self.client.post(
            self.package.get_absolute_url(),
            {
                "target": "@cliente.teste",
                "whatsapp": "11999999999",
                "confirm_public_profile": "on",
                "accept_terms": "on",
            },
        )
        self.assertContains(response, "abaixo do mínimo")
        self.assertFalse(Order.objects.exists())

    def test_profile_preview_returns_public_for_normal_username(self):
        response = self.client.get(
            reverse("store:profile_preview"),
            {"platform": "instagram", "target": "@cliente.teste"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "cliente.teste")
        self.assertEqual(response.json()["status"], "format_valid")
        self.assertIsNone(response.json()["is_public"])

    def test_profile_preview_returns_private_for_simulated_private_username(self):
        response = self.client.get(
            reverse("store:profile_preview"),
            {"platform": "instagram", "target": "@cliente_privado"},
        )
        self.assertEqual(response.status_code, 200)
        # Simulated provider only validates format; does not claim private/public
        self.assertEqual(response.json()["status"], "format_valid")
        self.assertIsNone(response.json()["is_public"])

    def test_profile_preview_returns_unknown_for_simulated_error(self):
        response = self.client.get(
            reverse("store:profile_preview"),
            {"platform": "instagram", "target": "@cliente_erro"},
        )
        self.assertEqual(response.status_code, 200)
        # Simulated provider only validates format; does not claim unknown/error
        self.assertEqual(response.json()["status"], "format_valid")
        self.assertIsNone(response.json()["is_public"])

    def test_checkout_does_not_lookup_or_save_profile_preview(self):
        order = self.checkout_order()
        self.assertEqual(order.profile_username, "")
        self.assertEqual(order.profile_picture_url, "")
        self.assertIsNone(order.profile_is_public)
        self.assertIsNone(order.profile_checked_at)

    def test_checkout_requires_terms_without_public_profile_checkbox(self):
        response = self.client.post(
            self.package.get_absolute_url(),
            {"target": "@cliente", "whatsapp": "11999999999"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não foi possível finalizar o pedido")
        self.assertContains(response, "Você precisa aceitar os Termos de Uso")
        self.assertNotContains(response, "Confirmo que meu perfil está público")
        self.assertFalse(Order.objects.exists())

    def test_checkout_target_field_adapts_to_service(self):
        followers = self.client.get(self.package.get_absolute_url())
        self.assertContains(followers, "Perfil")
        self.assertContains(followers, "@usuario ou link do perfil")

        likes = self.client.get(self.upsell_package.get_absolute_url())
        self.assertContains(likes, "Post ou Reels")
        self.assertContains(likes, "Cole o link do post ou Reels")

        comments = self.client.get(self.comments_package.get_absolute_url())
        self.assertContains(comments, "Link do vídeo ou publicação")
        self.assertContains(comments, "Cole o link do vídeo, Reels ou publicação")

    def test_instagram_followers_accept_username_formats(self):
        for target in (
            "@deividsh1",
            "https://www.instagram.com/deividsh1/",
        ):
            with self.subTest(target=target):
                response = self.post_checkout_target(self.package, target)
                order = Order.objects.get()
                self.assertRedirects(response, reverse("store:payment", args=[order.code]))
                Order.objects.all().delete()

    def test_instagram_followers_reject_username_without_at(self):
        response = self.post_checkout_target(self.package, "deividsh1")
        self.assertContains(response, "Formato inválido")
        self.assertFalse(Order.objects.exists())

    def test_instagram_followers_reject_spaces_and_long_username(self):
        for target in ("@abc def", "a" * 31, "https://www.instagram.com/deivid sh1/"):
            with self.subTest(target=target):
                response = self.post_checkout_target(self.package, target)
                self.assertContains(response, "Formato inválido")
                self.assertFalse(Order.objects.exists())

    def test_instagram_likes_require_publication_link(self):
        valid = self.post_checkout_target(
            self.upsell_package,
            "https://www.instagram.com/p/ABC123/",
        )
        order = Order.objects.get()
        self.assertRedirects(valid, reverse("store:payment", args=[order.code]))
        Order.objects.all().delete()

        invalid = self.post_checkout_target(self.upsell_package, "@deividsh1")
        self.assertContains(invalid, "Formato inválido")
        self.assertFalse(Order.objects.exists())

    def test_instagram_views_require_reels_link(self):
        views_package = self.create_views_catalog()[3000]
        valid = self.post_checkout_target(
            views_package,
            "https://www.instagram.com/reel/ABC123/",
        )
        order = Order.objects.get()
        self.assertRedirects(valid, reverse("store:payment", args=[order.code]))
        Order.objects.all().delete()

        invalid = self.post_checkout_target(views_package, "@deividsh1")
        self.assertContains(invalid, "Formato inválido")
        self.assertFalse(Order.objects.exists())

    def test_checkout_uses_local_format_feedback_only(self):
        response = self.client.get(self.package.get_absolute_url())
        self.assertContains(response, "Informe @ ou link do perfil.")
        self.assertNotContains(response, "Verificando perfil")
        self.assertNotContains(response, "Perfil encontrado")
        self.assertNotContains(response, "data-profile-preview-url")
        self.assertNotContains(response, "target-status-avatar")

    def test_checkout_package_picker_marks_current_and_links_siblings(self):
        response = self.client.get(self.upsell_package.get_absolute_url())
        self.assertContains(response, '<details class="checkout-package-picker">')
        self.assertNotContains(response, '<details class="checkout-package-picker" open>')
        self.assertContains(response, "Alterar pacote")
        self.assertContains(response, "Escolha outro pacote")
        self.assertContains(response, 'aria-current="true"')
        self.assertContains(response, self.second_upsell_package.get_absolute_url())

    def test_followers_have_paid_addons_without_free_gifts(self):
        response = self.client.get(self.package.get_absolute_url())
        self.assertNotContains(response, "Brindes inclusos")
        self.assertNotContains(response, 'data-bonus-target=""')
        self.assertContains(response, "Adicionais recomendados")
        self.assertContains(response, "Opcionais e pagos.")

    def test_simulated_checkout_redirects_and_payment_shows_pix(self):
        order = self.checkout_order()
        payment = self.client.get(reverse("store:payment", args=[order.code]))
        self.assertContains(payment, "Pagamento via Pix")
        self.assertContains(payment, f"PIX-SIMULADO-{order.code}")
        self.assertContains(payment, "Pix copia e cola")

    def test_checkout_rejects_wrong_platform_link(self):
        response = self.client.post(
            self.package.get_absolute_url(),
            {
                "target": "https://example.com/perfil",
                "whatsapp": "11999999999",
                "confirm_public_profile": "on",
                "accept_terms": "on",
            },
        )
        self.assertContains(response, "Formato inválido")
        self.assertFalse(Order.objects.exists())

    def test_checkout_validates_whatsapp_and_email(self):
        response = self.client.post(
            self.package.get_absolute_url(),
            {
                "target": "@cliente.teste",
                "whatsapp": "123",
                "email": "email-invalido",
                "confirm_public_profile": "on",
                "accept_terms": "on",
            },
        )
        self.assertIn("whatsapp", response.context["form"].errors)
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(Order.objects.exists())

    @override_settings(ORDER_EMAIL_REQUIRED=True)
    def test_checkout_requires_email_and_shows_commercial_layout(self):
        response = self.client.post(
            self.package.get_absolute_url(),
            {
                "target": "@cliente.teste",
                "whatsapp": "11999999999",
                "confirm_public_profile": "on",
                "accept_terms": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Informe um email válido para receber atualizações do pedido."
        )
        self.assertContains(response, "Opcionais e pagos.")
        self.assertContains(response, "Total a pagar")
        self.assertContains(response, "Finalizar e gerar Pix")
        self.assertContains(response, "Consultar pedido")
        self.assertContains(response, reverse("store:order_lookup"))
        self.assertFalse(Order.objects.exists())

    def test_valid_webhook_pays_and_dispatches_only_once(self):
        order = self.checkout_order(with_upsell=True)
        charge = order.payment_logs.get(event_type=PaymentLog.EventType.CHARGE)
        payload = {
            "id": charge.external_payment_id,
            "status": "paid",
            "external_reference": order.code,
            "amount": "44.80",
        }
        for _ in range(2):
            response = self.client.post(
                reverse("store:payment_webhook"),
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_WEBHOOK_SECRET="test-webhook-secret",
            )
            self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.SUBMITTED)
        self.assertEqual(order.provider_status, "simulated")
        self.assertEqual(ProviderLog.objects.filter(action="submit_simulated").count(), 2)
        self.assertEqual(
            OrderItem.objects.filter(
                fulfillment_status=Order.FulfillmentStatus.SUBMITTED
            ).count(),
            2,
        )

    def test_webhook_rejects_invalid_secret(self):
        order = self.checkout_order()
        charge = order.payment_logs.get(event_type=PaymentLog.EventType.CHARGE)
        response = self.client.post(
            reverse("store:mercadopago_webhook"),
            data=json.dumps(
                {
                    "id": charge.external_payment_id,
                    "status": "paid",
                    "external_reference": order.code,
                    "amount": "29.90",
                }
            ),
            content_type="application/json",
            HTTP_X_WEBHOOK_SECRET="wrong",
        )
        self.assertEqual(response.status_code, 401)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_mercado_pago_webhook_queries_payment_and_dispatches_once(self):
        order = self.checkout_order()
        charge = order.payment_logs.get(event_type=PaymentLog.EventType.CHARGE)
        payment_id = "123456789"
        order.external_payment_id = payment_id
        order.save(update_fields=("external_payment_id", "updated_at"))
        charge.external_payment_id = payment_id
        charge.save(update_fields=("external_payment_id",))

        request_id = "request-123"
        timestamp = str(int(time.time()))
        secret = "mercado-pago-webhook-secret-long"
        manifest = f"id:{payment_id};request-id:{request_id};ts:{timestamp};"
        signature = hmac.new(
            secret.encode(), manifest.encode(), hashlib.sha256
        ).hexdigest()
        payment = {
            "id": payment_id,
            "external_payment_id": payment_id,
            "external_reference": order.code,
            "status": "approved",
            "amount": order.amount_brl,
            "raw": {"id": payment_id, "status": "approved"},
        }

        with self.settings(
            PAYMENT_SIMULATED=False,
            PAYMENT_PROVIDER="mercadopago",
            MERCADO_PAGO_WEBHOOK_SECRET=secret,
        ), patch(
            "store.services.payment_api.get_payment_status", return_value=payment
        ) as get_status:
            for _ in range(2):
                response = self.client.post(
                    f"{reverse('store:mercadopago_webhook')}?data.id={payment_id}&type=payment",
                    data=json.dumps({"type": "payment", "data": {"id": payment_id}}),
                    content_type="application/json",
                    HTTP_X_SIGNATURE=f"ts={timestamp},v1={signature}",
                    HTTP_X_REQUEST_ID=request_id,
                )
                self.assertEqual(response.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.SUBMITTED)
        self.assertEqual(ProviderLog.objects.filter(action="submit_simulated").count(), 1)
        self.assertEqual(get_status.call_count, 2)

    def test_mercado_pago_webhook_returns_retryable_error_when_status_api_fails(self):
        order = self.checkout_order()
        charge = order.payment_logs.get(event_type=PaymentLog.EventType.CHARGE)
        payment_id = "123456789"
        order.external_payment_id = payment_id
        order.save(update_fields=("external_payment_id", "updated_at"))
        charge.external_payment_id = payment_id
        charge.save(update_fields=("external_payment_id",))

        request_id = "request-123"
        timestamp = str(int(time.time()))
        secret = "mercado-pago-webhook-secret-long"
        manifest = f"id:{payment_id};request-id:{request_id};ts:{timestamp};"
        signature = hmac.new(
            secret.encode(), manifest.encode(), hashlib.sha256
        ).hexdigest()

        with self.settings(
            PAYMENT_SIMULATED=False,
            PAYMENT_PROVIDER="mercadopago",
            MERCADO_PAGO_WEBHOOK_SECRET=secret,
        ), patch(
            "store.services.payment_api.get_payment_status",
            side_effect=PaymentAPIError("indisponível"),
        ):
            response = self.client.post(
                f"{reverse('store:mercadopago_webhook')}?data.id={payment_id}&type=payment",
                data=json.dumps({"type": "payment", "data": {"id": payment_id}}),
                content_type="application/json",
                HTTP_X_SIGNATURE=f"ts={timestamp},v1={signature}",
                HTTP_X_REQUEST_ID=request_id,
            )

        self.assertEqual(response.status_code, 503)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_manual_payment_verification_is_idempotent(self):
        order = self.checkout_order()
        charge = order.payment_logs.get(event_type=PaymentLog.EventType.CHARGE)
        payment_id = "987654321"
        order.external_payment_id = payment_id
        order.save(update_fields=("external_payment_id", "updated_at"))
        charge.external_payment_id = payment_id
        charge.save(update_fields=("external_payment_id",))
        payment = {
            "id": payment_id,
            "external_payment_id": payment_id,
            "external_reference": order.code,
            "status": "approved",
            "amount": order.amount_brl,
            "signature_valid": True,
            "raw": {"id": payment_id, "status": "approved"},
        }

        with patch("store.views.get_payment_status", return_value=payment):
            for _ in range(2):
                response = self.client.post(reverse("store:verify_payment", args=[order.code]))
                self.assertRedirects(response, reverse("store:payment", args=[order.code]))

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(ProviderLog.objects.filter(action="submit_simulated").count(), 1)
        self.assertEqual(
            order.payment_logs.filter(event_type=PaymentLog.EventType.STATUS).count(), 1
        )

    def test_wrong_amount_never_dispatches(self):
        order = self.checkout_order()
        charge = order.payment_logs.get(event_type=PaymentLog.EventType.CHARGE)
        accepted = process_payment_notification(
            {
                "external_payment_id": charge.external_payment_id,
                "status": "paid",
                "external_reference": order.code,
                "amount": Decimal("1.00"),
                "signature_valid": True,
                "raw": {},
            }
        )
        self.assertFalse(accepted)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertTrue(
            order.payment_logs.filter(
                event_type=PaymentLog.EventType.ERROR,
                response_data={"reason": "payment_amount_mismatch"},
            ).exists()
        )

    def test_pending_order_is_never_dispatched(self):
        order = self.checkout_order()
        self.assertFalse(dispatch_paid_order(order.id))
        self.assertFalse(ProviderLog.objects.exists())
        self.assertFalse(order.items.exclude(fulfillment_status="pending").exists())

    @patch(
        "store.services.order_processing.submit_order",
        side_effect=ProviderAPIError("detalhe técnico sensível"),
    )
    def test_provider_error_log_is_safe(self, submit):
        order = self.checkout_order()
        order.mark_paid()
        order.save(update_fields=("payment_status", "paid_at", "updated_at"))
        self.assertFalse(dispatch_paid_order(order.id))
        log = ProviderLog.objects.get(action="submit_error")
        self.assertNotIn("sensível", log.message)
        self.assertEqual(log.response_data, {"reason": "provider_request_failed"})
        submit.assert_called_once()

    @patch(
        "store.services.order_processing.submit_order",
        side_effect=ProviderAPIError("resposta incerta do fornecedor"),
    )
    def test_duplicate_notification_does_not_retry_provider_error(self, submit):
        order = self.checkout_order()
        charge = order.payment_logs.get(event_type=PaymentLog.EventType.CHARGE)
        notification = {
            "external_payment_id": charge.external_payment_id,
            "status": "paid",
            "external_reference": order.code,
            "amount": order.amount_brl,
            "signature_valid": True,
            "raw": {},
        }

        self.assertTrue(process_payment_notification(notification))
        self.assertTrue(process_payment_notification(notification))

        order.refresh_from_db()
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.ERROR)
        submit.assert_called_once()

    @patch("store.services.order_processing.submit_order")
    def test_admin_retry_can_reprocess_provider_error(self, submit):
        order = self.checkout_order()
        order.mark_paid()
        order.fulfillment_status = Order.FulfillmentStatus.ERROR
        order.save(
            update_fields=(
                "payment_status",
                "paid_at",
                "fulfillment_status",
                "updated_at",
            )
        )
        item = order.items.get()
        item.fulfillment_status = Order.FulfillmentStatus.ERROR
        item.save(update_fields=("fulfillment_status",))
        submit.return_value = {"order": "123", "status": "submitted"}

        self.assertTrue(dispatch_paid_order(order.id, retry_errors=True))

        order.refresh_from_db()
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.SUBMITTED)
        submit.assert_called_once()

    def test_lookup_requires_matching_contact(self):
        order = self.checkout_order()
        response = self.client.post(
            reverse("store:order_lookup"),
            {"code": order.code, "contact": "(11) 99999-9999"},
        )
        self.assertEqual(response.context["order"], order)
        response = self.client.post(
            reverse("store:order_lookup"),
            {"code": order.code, "contact": "wrong@example.com"},
        )
        self.assertIsNone(response.context["order"])

    def test_rate_limit_blocks_repeated_checkout_attempts(self):
        response = None
        for _ in range(9):
            response = self.client.post(
                self.package.get_absolute_url(),
                {"target": "@cliente", "whatsapp": "11999999999"},
            )
        self.assertEqual(response.status_code, 429)

    def test_sensitive_pages_disable_browser_cache(self):
        response = self.client.get(self.package.get_absolute_url())
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertIn("Content-Security-Policy", response.headers)


@override_settings(
    PROVIDER_API_URL="https://provider.example/api",
    PROVIDER_API_KEY="test-key",
    PROVIDER_SIMULATED=False,
)
class ProviderAPITests(TestCase):
    @patch("store.services.provider_api.requests.post")
    def test_supported_provider_operations(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            [{"service": 1, "name": "Followers"}],
            {"status": "In progress"},
            {"balance": "100.00", "currency": "USD"},
        ]
        self.assertEqual(list_services()[0]["service"], 1)
        self.assertEqual(get_order_status("10")["status"], "In progress")
        self.assertEqual(get_balance()["currency"], "USD")
        self.assertEqual(post.call_args_list[0].kwargs["data"]["action"], "services")
        self.assertEqual(post.call_args_list[0].kwargs["data"]["key"], "test-key")
        self.assertEqual(post.call_args_list[1].kwargs["data"]["order"], "10")
        self.assertEqual(post.call_args_list[0].kwargs["timeout"], 20)

    @patch("store.services.provider_api.requests.post")
    def test_multiple_refill_and_cancel_operations_use_expected_parameters(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            {"1": {"status": "Completed"}, "2": {"status": "In progress"}},
            {"refill": "11"},
            [{"order": 1, "refill": 11}, {"order": 2, "refill": 12}],
            {"status": "Completed"},
            [{"refill": 11, "status": "Completed"}],
            [{"order": 1, "cancel": 1}, {"order": 2, "cancel": 1}],
        ]

        get_multiple_order_status([1, 2])
        create_refill(1)
        create_multiple_refill([1, 2])
        get_refill_status(11)
        get_multiple_refill_status([11, 12])
        cancel_orders([1, 2])

        payloads = [call.kwargs["data"] for call in post.call_args_list]
        self.assertEqual(payloads[0]["orders"], "1,2")
        self.assertEqual(payloads[1]["order"], 1)
        self.assertEqual(payloads[2]["orders"], "1,2")
        self.assertEqual(payloads[3]["refill"], 11)
        self.assertEqual(payloads[4]["refills"], "11,12")
        self.assertEqual(payloads[5]["orders"], "1,2")
        self.assertEqual(
            [payload["action"] for payload in payloads],
            ["status", "refill", "refill", "refill_status", "refill_status", "cancel"],
        )
        self.assertFalse(
            {"chave", "ação", "pedido", "equilíbrio"}.intersection(payloads[0])
        )

    @patch("store.services.provider_api.requests.post")
    def test_multiple_operations_reject_more_than_100_ids(self, post):
        with self.assertRaises(ProviderAPIError):
            get_multiple_order_status(range(101))
        post.assert_not_called()

    @patch("store.services.provider_api.requests.post")
    def test_provider_error_response_raises_safe_exception(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"error": "Sensitive provider detail"}
        with self.assertRaises(ProviderAPIError):
            get_balance()

    @patch("store.services.provider_api.ProviderLog.objects.create")
    @patch("store.services.provider_api.requests.post")
    def test_custom_comments_are_sent_only_when_present(self, post, create_log):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"order": 99}
        item = SimpleNamespace(
            provider_service_id="1723",
            target="https://www.instagram.com/p/publicacao/",
            quantity=5,
            comments_text="Um\nDois\nTrês\nQuatro\nCinco",
        )
        result = submit_order(item)
        self.assertEqual(result["order"], "99")
        self.assertEqual(post.call_args.kwargs["data"]["action"], "add")
        self.assertEqual(post.call_args.kwargs["data"]["service"], "1723")
        self.assertEqual(post.call_args.kwargs["data"]["comments"], item.comments_text)
        create_log.assert_called_once()

        post.reset_mock()
        item.comments_text = ""
        submit_order(item)
        self.assertNotIn("comments", post.call_args.kwargs["data"])

    @override_settings(
        PROVIDER_API_URL="https://provider.example/api",
        PROVIDER_API_KEY="test-key",
        PROVIDER_SIMULATED=False,
    )
    @patch("store.management.commands.test_smmcost.list_services")
    @patch("store.management.commands.test_smmcost.get_balance")
    def test_safe_provider_command_only_checks_balance_and_services(
        self, get_balance_mock, list_services_mock
    ):
        get_balance_mock.return_value = {"balance": "10.00", "currency": "USD"}
        list_services_mock.return_value = [
            {"service": service_id} for service_id in ("9142", "10635", "8061")
        ]
        output = StringIO()

        call_command("test_smmcost", stdout=output)

        result = output.getvalue()
        self.assertIn("API key configurada: sim", result)
        self.assertNotIn("test-key", result)
        self.assertIn("Nenhum pedido será criado", result)
        get_balance_mock.assert_called_once_with()
        list_services_mock.assert_called_once_with()


@override_settings(
    PAYMENT_SIMULATED=False,
    PAYMENT_PROVIDER="mercadopago",
    MERCADO_PAGO_API_URL="https://api.mercadopago.com",
    MERCADO_PAGO_ACCESS_TOKEN="test-access-token",
    MERCADO_PAGO_WEBHOOK_SECRET="a-long-test-webhook-secret",
    PUBLIC_BASE_URL="https://shop.example",
)
class PaymentAPITests(TestCase):
    @patch("store.services.payment_api.requests.request")
    def test_create_pix_charge_is_idempotent_and_normalized(self, request):
        request.return_value.json.return_value = {
            "id": "pay-1",
            "status": "pending",
            "transaction_amount": 29.90,
            "external_reference": "ORDER123",
            "payer": {"email": "client@example.com"},
            "point_of_interaction": {
                "transaction_data": {
                    "qr_code": "pix-code",
                    "qr_code_base64": "base64-code",
                    "ticket_url": "https://payments.example/ticket",
                }
            },
        }
        order = SimpleNamespace(
            code="ORDER123",
            amount_brl=Decimal("29.90"),
            service_name="Seguidores",
            email="client@example.com",
            whatsapp="11999999999",
        )
        result = create_pix_charge(order)
        self.assertEqual(result["id"], "pay-1")
        self.assertEqual(result["pix_code"], "pix-code")
        self.assertEqual(request.call_args.args[:2], ("POST", "https://api.mercadopago.com/v1/payments"))
        self.assertIn("X-Idempotency-Key", request.call_args.kwargs["headers"])
        self.assertEqual(request.call_args.kwargs["json"]["payment_method_id"], "pix")
        self.assertEqual(
            request.call_args.kwargs["json"]["notification_url"],
            "https://shop.example/webhooks/mercadopago/",
        )
        self.assertEqual(result["raw"]["payer"], {"email": "[protegido]"})

    @patch("store.services.payment_api.requests.request")
    def test_get_payment_status_uses_official_endpoint(self, request):
        request.return_value.json.return_value = {
            "id": 123,
            "status": "approved",
            "transaction_amount": 29.90,
            "external_reference": "ORDER123",
            "point_of_interaction": {"transaction_data": {}},
        }
        result = get_payment_status("123")
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["amount"], Decimal("29.90"))
        self.assertEqual(
            request.call_args.args[:2],
            ("GET", "https://api.mercadopago.com/v1/payments/123"),
        )


class CatalogMaintenanceTests(TestCase):
    def test_order_has_required_database_fields(self):
        field_names = {field.name for field in Order._meta.fields}
        self.assertTrue(
            {
                "code",
                "package",
                "quantity",
                "amount_brl",
                "target",
                "whatsapp",
                "email",
                "payment_status",
                "provider_status",
                "external_payment_id",
                "external_order_id",
                "provider_service_id",
                "customer_ip",
                "customer_user_agent",
                "accepted_terms",
                "accepted_terms_at",
                "confirmed_public_profile",
                "profile_username",
                "profile_picture_url",
                "profile_is_public",
                "profile_checked_at",
                "created_at",
                "updated_at",
            }.issubset(field_names)
        )

    def test_seed_has_only_requested_active_services(self):
        call_command("seed_demo", verbosity=0)
        self.assertEqual(
            list(
                Service.objects.filter(active=True)
                .order_by("platform__position", "position")
                .values_list("platform__slug", "name", "provider_service_id")
            ),
            [
                ("instagram", "Seguidores Instagram", "9142"),
                ("instagram", "Curtidas Instagram", "10635"),
                ("instagram", "Visualizações Instagram Reels", "8061"),
                ("instagram", "Comentários Personalizados Instagram", "1723"),
                ("tiktok", "Seguidores TikTok", "9542"),
                ("tiktok", "Curtidas TikTok", "10466"),
                ("tiktok", "Visualizações TikTok", "10641"),
            ],
        )
        comments = Service.objects.get(provider_service_id="1723")
        self.assertTrue(comments.requires_comments)
        self.assertEqual(comments.packages.filter(active=True).count(), 6)
        likes = Service.objects.get(provider_service_id="10635")
        pending_price = likes.packages.get(quantity=10000)
        self.assertFalse(pending_price.active)
        self.assertEqual(pending_price.price_brl, Decimal("0.00"))

    def test_disable_brazilian_services_preserves_records(self):
        platform = Platform.objects.create(name="Instagram", slug="instagram")
        service = Service.objects.create(
            platform=platform,
            name="Seguidores Brasileiros",
            slug="seguidores-brasileiros",
            active=True,
        )
        package = Package.objects.create(
            service=service,
            name="100",
            quantity=100,
            price_brl=Decimal("10.00"),
            active=True,
        )
        call_command("disable_brazilian_services", verbosity=0)
        service.refresh_from_db()
        package.refresh_from_db()
        self.assertFalse(service.active)
        self.assertFalse(package.active)
