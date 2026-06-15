from decimal import Decimal

from django.core.management.base import BaseCommand

from store.models import Package, Platform, Service


CATALOG = {
    "instagram": {
        "name": "Instagram",
        "description": "Pacotes para fortalecer sua presença no Instagram.",
        "position": 1,
        "services": [
            {
                "name": "Seguidores Instagram",
                "slug": "seguidores-instagram",
                "technical_id": "9142",
                "description": "Seguidores internacionais e nacionais, com início a partir de 10 minutos após a confirmação do pagamento. Não pedimos sua senha.",
                "packages": [
                    ("500 Seguidores Mundiais", 500, "12.90"),
                    ("1.000 Seguidores Mundiais", 1000, "17.90"),
                    ("2.000 Seguidores Mundiais", 2000, "32.90"),
                    ("3.000 Seguidores Mundiais", 3000, "44.90"),
                    ("5.000 Seguidores Mundiais", 5000, "84.90"),
                    ("10.000 Seguidores Mundiais", 10000, "129.90"),
                    ("20.000 Seguidores Mundiais", 20000, "249.00"),
                    ("30.000 Seguidores Mundiais", 30000, "359.90"),
                ],
            },
            {
                "name": "Curtidas Instagram",
                "slug": "curtidas-instagram",
                "technical_id": "10635",
                "description": "Curtidas para publicações do Instagram, com início a partir de 5 minutos após a confirmação do pagamento.",
                "packages": [
                    ("250 Curtidas", 250, "4.90"),
                    ("500 Curtidas", 500, "7.90"),
                    ("1.000 Curtidas", 1000, "12.90"),
                    ("2.200 Curtidas", 2200, "18.99"),
                    ("3.000 Curtidas", 3000, "24.99"),
                    ("5.000 Curtidas", 5000, "39.99"),
                    ("10.000 Curtidas", 10000, "0.00", False),
                ],
            },
            {
                "name": "Visualizações Instagram Reels",
                "slug": "visualizacoes-instagram-reels",
                "technical_id": "8061",
                "description": "Visualizações para Reels do Instagram, com entrega rápida após aprovação do pagamento.",
                "packages": [
                    ("3.000 Visualizações em Reels", 3000, "6.18"),
                    ("5.000 Visualizações em Reels", 5000, "10.00"),
                    ("10.000 Visualizações em Reels", 10000, "14.00"),
                    ("20.000 Visualizações em Reels", 20000, "25.00"),
                    ("50.000 Visualizações em Reels", 50000, "35.90"),
                    ("100.000 Visualizações em Reels", 100000, "55.90"),
                    ("500.000 Visualizações em Reels", 500000, "99.90"),
                    ("1.000.000 Visualizações em Reels", 1000000, "139.99"),
                ],
            },
            {
                "name": "Comentários Personalizados Instagram",
                "slug": "comentarios-personalizados-instagram",
                "technical_id": "1723",
                "requires_comments": True,
                "description": "Comentários personalizados para fotos e vídeos do Instagram. Escreva um comentário por linha no checkout. Início a partir de 1 hora após a confirmação do pagamento.",
                "packages": [
                    ("5 Comentários Personalizados", 5, "5.90"),
                    ("10 Comentários Personalizados", 10, "10.90"),
                    ("20 Comentários Personalizados", 20, "20.90"),
                    ("30 Comentários Personalizados", 30, "30.90"),
                    ("50 Comentários Personalizados", 50, "44.90"),
                    ("100 Comentários Personalizados", 100, "79.90"),
                ],
            },
        ],
    },
    "tiktok": {
        "name": "TikTok",
        "description": "Pacotes de crescimento para seu perfil no TikTok.",
        "position": 2,
        "services": [
            {
                "name": "Seguidores TikTok",
                "slug": "seguidores",
                "technical_id": "9542",
                "description": "Seguidores para TikTok, com início a partir de 10 minutos após confirmação do pagamento.",
                "packages": [
                    ("100 Seguidores TikTok", 100, "14.90"),
                    ("500 Seguidores TikTok", 500, "49.90"),
                    ("1.000 Seguidores TikTok", 1000, "79.90"),
                    ("2.000 Seguidores TikTok", 2000, "149.90"),
                    ("5.000 Seguidores TikTok", 5000, "299.90"),
                ],
            },
            {
                "name": "Curtidas TikTok",
                "slug": "curtidas",
                "technical_id": "10466",
                "description": "Curtidas para vídeos do TikTok, com início a partir de 5 minutos após confirmação do pagamento.",
                "packages": [
                    ("100 Curtidas TikTok", 100, "8.90"),
                    ("500 Curtidas TikTok", 500, "24.90"),
                    ("1.000 Curtidas TikTok", 1000, "39.90"),
                    ("2.000 Curtidas TikTok", 2000, "69.90"),
                    ("5.000 Curtidas TikTok", 5000, "139.90"),
                ],
            },
            {
                "name": "Visualizações TikTok",
                "slug": "visualizacoes",
                "technical_id": "10641",
                "description": "Visualizações para vídeos do TikTok, com entrega rápida após confirmação do pagamento.",
                "packages": [
                    ("1.000 Visualizações TikTok", 1000, "14.90"),
                    ("5.000 Visualizações TikTok", 5000, "39.90"),
                    ("10.000 Visualizações TikTok", 10000, "69.90"),
                    ("50.000 Visualizações TikTok", 50000, "149.90"),
                    ("100.000 Visualizações TikTok", 100000, "249.90"),
                ],
            },
        ],
    },
}


class Command(BaseCommand):
    help = "Cria o catálogo inicial da WebMaster."

    def handle(self, *args, **options):
        for platform_slug, platform_data in CATALOG.items():
            platform, _ = Platform.objects.update_or_create(
                slug=platform_slug,
                defaults={
                    "name": platform_data["name"],
                    "description": platform_data["description"],
                    "position": platform_data["position"],
                    "active": True,
                },
            )
            active_slugs = []
            for service_position, service_data in enumerate(
                platform_data["services"], start=1
            ):
                active_slugs.append(service_data["slug"])
                technical_id = service_data["technical_id"]
                service = None
                if technical_id:
                    service = platform.services.filter(
                        provider_service_id=technical_id
                    ).first()
                if not service:
                    service = platform.services.filter(slug=service_data["slug"]).first()
                if not service:
                    service = Service(platform=platform)
                service.name = service_data["name"]
                service.slug = service_data["slug"]
                service.description = service_data["description"]
                service.provider_service_id = technical_id
                service.min_quantity = service_data.get("min_quantity")
                service.max_quantity = service_data.get("max_quantity")
                service.requires_comments = service_data.get("requires_comments", False)
                service.position = service_position
                service.active = True
                service.save()

                package_quantities = []
                for package_position, package_data in enumerate(
                    service_data["packages"], start=1
                ):
                    name, quantity, price, *active_value = package_data
                    active = active_value[0] if active_value else True
                    package_quantities.append(quantity)
                    Package.objects.update_or_create(
                        service=service,
                        quantity=quantity,
                        defaults={
                            "name": name,
                            "price_brl": Decimal(price),
                            "active": active,
                            "featured": active and package_position == 2,
                            "position": package_position,
                        },
                    )
                service.packages.exclude(quantity__in=package_quantities).update(active=False)
            inactive_services = platform.services.exclude(slug__in=active_slugs)
            Package.objects.filter(service__in=inactive_services).update(active=False)
            inactive_services.update(active=False)
        self.stdout.write(self.style.SUCCESS("Catálogo inicial criado."))
