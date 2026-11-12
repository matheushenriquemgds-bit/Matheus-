from django.core.management.base import BaseCommand
from django.utils import timezone

from whatsapp import bot
from whatsapp.models import Conversa, Mensagem

TELEFONE_TESTE = "0000000000000"


class Command(BaseCommand):
    help = ("Conversa com o robô pelo terminal, sem WhatsApp, para testar as respostas. Precisa só da "
            "ANTHROPIC_API_KEY. Os pedidos criados aparecem no sistema, na conversa \"Teste pelo terminal\".")

    def add_arguments(self, parser):
        parser.add_argument("--nova", action="store_true", help="Apaga a conversa de teste anterior e começa do zero")

    def handle(self, *args, **opcoes):
        if opcoes["nova"]:
            Conversa.objects.filter(telefone=TELEFONE_TESTE).delete()
        conversa, _ = Conversa.objects.get_or_create(telefone=TELEFONE_TESTE, defaults={"nome": "Teste pelo terminal"})
        self.stdout.write("Escreva como se fosse o cliente. Ctrl+C ou 'sair' para encerrar.\n")
        while True:
            try:
                texto = input("Você: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if texto.lower() in ("sair", "exit"):
                break
            if not texto:
                continue
            agora = timezone.now()
            Mensagem.objects.create(conversa=conversa, direcao=Mensagem.ENTRADA, autor=Mensagem.CONTATO,
                                    texto=texto, criada_em=agora)
            conversa.ultima_mensagem_em = conversa.ultima_entrada_em = agora
            conversa.save()
            if conversa.bot_pausado:
                self.stdout.write(self.style.WARNING("(conversa com a equipe: o robô não responde)\n"))
                continue
            resposta = bot.gerar_resposta(conversa)
            conversa.refresh_from_db()
            Mensagem.objects.create(conversa=conversa, direcao=Mensagem.SAIDA, autor=Mensagem.ROBO, texto=resposta)
            self.stdout.write(self.style.SUCCESS(f"Robô: {resposta}\n"))
            for s in conversa.solicitacoes.filter(criado_em__gte=agora):
                self.stdout.write(self.style.NOTICE(f"  [registrado: {s}]\n"))
