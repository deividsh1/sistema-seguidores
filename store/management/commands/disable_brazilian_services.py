from django.core.management.base import BaseCommand

from store.models import Service


BRAZILIAN_SERVICE_NAMES = (
    "Comentários Brasileiros",
    "Curtidas Brasileiras",
    "Seguidores Brasileiros",
)


class Command(BaseCommand):
    help = "Desativa serviços brasileiros e seus pacotes sem apagar pedidos históricos."

    def handle(self, *args, **options):
        services = Service.objects.filter(name__in=BRAZILIAN_SERVICE_NAMES)
        package_count = 0
        for service in services:
            package_count += service.packages.filter(active=True).update(active=False)
        service_count = services.filter(active=True).update(active=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"{service_count} serviço(s) e {package_count} pacote(s) desativado(s)."
            )
        )
