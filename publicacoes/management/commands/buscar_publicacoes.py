"""Busca publicações de todas as OABs ativas. Agende no cron, por exemplo:

    0 7,13,19 * * 1-5  cd /caminho/do/projeto && python manage.py buscar_publicacoes
"""

from datetime import date

from django.core.management.base import BaseCommand

from publicacoes import servicos


class Command(BaseCommand):
    help = "Busca publicações (DJEN / Comunica PJe) das OABs monitoradas."

    def add_arguments(self, parser):
        parser.add_argument("--inicio", type=date.fromisoformat, help="Data inicial (AAAA-MM-DD)")
        parser.add_argument("--fim", type=date.fromisoformat, help="Data final (AAAA-MM-DD)")

    def handle(self, *args, inicio=None, fim=None, **options):
        novas, erros = servicos.buscar_todas(inicio, fim)
        for erro in erros:
            self.stderr.write(self.style.ERROR(erro))
        self.stdout.write(self.style.SUCCESS(f"{novas} nova(s) publicação(ões)."))
        if erros:
            raise SystemExit(1)
