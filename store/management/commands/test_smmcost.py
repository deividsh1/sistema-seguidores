from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from store.services.provider_api import ProviderAPIError, get_balance, list_services


EXPECTED_SERVICES = {
    "9142": "Instagram Seguidores",
    "10635": "Instagram Curtidas",
    "8061": "Instagram Visualizações",
    "9542": "TikTok Seguidores",
    "10466": "TikTok Curtidas",
    "10641": "TikTok Visualizações",
    "1723": "Instagram Comentários Personalizados",
}


class Command(BaseCommand):
    help = "Testa conexão, saldo e catálogo da integração sem criar pedidos."

    def handle(self, *args, **options):
        self.stdout.write(f"URL configurada: {'sim' if settings.PROVIDER_API_URL else 'não'}")
        self.stdout.write(
            f"API key configurada: {'sim' if settings.PROVIDER_API_KEY else 'não'}"
        )
        self.stdout.write(f"PROVIDER_SIMULATED: {settings.PROVIDER_SIMULATED}")
        self.stdout.write("Ações seguras: balance, services. Nenhum pedido será criado.")

        if not settings.PROVIDER_API_URL or not settings.PROVIDER_API_KEY:
            raise CommandError("Configure PROVIDER_API_URL e PROVIDER_API_KEY no .env.")

        try:
            balance = get_balance()
            services = list_services()
        except ProviderAPIError as exc:
            raise CommandError(str(exc)) from exc

        received_ids = {
            str(service.get("service"))
            for service in services
            if isinstance(service, dict) and service.get("service") is not None
        }
        found = [
            f"{service_id} - {name}"
            for service_id, name in EXPECTED_SERVICES.items()
            if service_id in received_ids
        ]
        missing = [
            f"{service_id} - {name}"
            for service_id, name in EXPECTED_SERVICES.items()
            if service_id not in received_ids
        ]

        self.stdout.write(self.style.SUCCESS("OK: conexão realizada."))
        self.stdout.write(
            f"Saldo: {balance.get('balance', 'indisponível')} "
            f"{balance.get('currency', '')}".rstrip()
        )
        self.stdout.write(f"Serviços recebidos: {len(services)}")
        self.stdout.write("IDs encontrados:")
        for service in found:
            self.stdout.write(self.style.SUCCESS(f"  OK {service}"))
        self.stdout.write("IDs não encontrados:")
        if missing:
            for service in missing:
                self.stdout.write(self.style.WARNING(f"  AUSENTE {service}"))
        else:
            self.stdout.write(self.style.SUCCESS("  Nenhum."))
