from django.core.management.base import BaseCommand, CommandError

from store.services.provider_api import ProviderAPIError, list_services


class Command(BaseCommand):
    help = "Lista IDs técnicos disponíveis na integração de entrega."

    def add_arguments(self, parser):
        parser.add_argument(
            "--search",
            default="",
            help="Filtra por texto no nome ou categoria, por exemplo Instagram.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Número máximo de resultados exibidos.",
        )

    def handle(self, *args, **options):
        try:
            services = list_services()
        except ProviderAPIError as exc:
            raise CommandError(str(exc)) from exc

        search = options["search"].lower().strip()
        if search:
            services = [
                service
                for service in services
                if search
                in f"{service.get('category', '')} {service.get('name', '')}".lower()
            ]

        self.stdout.write("ID | CATEGORIA | SERVIÇO | TAXA | MIN | MAX")
        for service in services[: options["limit"]]:
            self.stdout.write(
                f"{service.get('service')} | {service.get('category')} | "
                f"{service.get('name')} | {service.get('rate')} | "
                f"{service.get('min')} | {service.get('max')}"
            )
        self.stdout.write(self.style.SUCCESS(f"{len(services)} serviço(s) encontrado(s)."))
