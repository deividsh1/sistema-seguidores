from django.core.management.base import BaseCommand, CommandError

from store.services.provider_api import ProviderAPIError, get_balance


class Command(BaseCommand):
    help = "Consulta o saldo atual da integração de entrega."

    def handle(self, *args, **options):
        try:
            data = get_balance()
        except ProviderAPIError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Saldo: {data.get('balance')} {data.get('currency')}")
        )
