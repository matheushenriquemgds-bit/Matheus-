"""Cria dados fictícios para conhecer o sistema: python manage.py dados_demo"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from agenda.models import Compromisso
from clientes.models import Cliente
from core.utils import digito_verificador_cnj, formatar_cnj
from financeiro.models import Lancamento
from processos.models import Andamento, Processo
from publicacoes.models import OABMonitorada, Publicacao
from publicacoes.servicos import registrar


def cnj(sequencial, ano, tribunal="826", origem="0100"):
    base = f"{sequencial:07d}00{ano}{tribunal}{origem}"
    return formatar_cnj(f"{sequencial:07d}{digito_verificador_cnj(base):02d}{ano}{tribunal}{origem}")


class Command(BaseCommand):
    help = "Popula o banco com dados fictícios de demonstração."

    def handle(self, *args, **options):
        if Cliente.objects.exists():
            self.stdout.write("Já existem clientes cadastrados; nada foi feito.")
            return
        hoje = timezone.localdate()
        user = get_user_model().objects.filter(is_superuser=True).first()

        maria = Cliente.objects.create(nome="Maria Aparecida Souza", cpf_cnpj="12345678909", celular="(11) 98888-1111",
                                       email="maria@exemplo.com", cidade="São Paulo", uf="SP", responsavel=user)
        padaria = Cliente.objects.create(tipo=Cliente.PJ, nome="Padaria Pão Quente Ltda.", cpf_cnpj="11222333000181",
                                         telefone="(11) 3333-4444", cidade="Campinas", uf="SP", responsavel=user)
        jose = Cliente.objects.create(nome="José Carlos Pereira", cpf_cnpj="98765432100", celular="(21) 97777-2222",
                                      cidade="Rio de Janeiro", uf="RJ", responsavel=user)

        p1 = Processo.objects.create(numero=cnj(1234, 2025), cliente=maria, parte_contraria="Banco Exemplo S.A.",
                                     titulo="Ação revisional de contrato", area="consumidor", tribunal="TJSP",
                                     orgao="5ª Vara Cível", comarca="São Paulo", valor_causa=48000, responsavel=user)
        p2 = Processo.objects.create(numero=cnj(5678, 2024, "502", "0011"), cliente=jose,
                                     parte_contraria="Transportes Rápidos Ltda.", titulo="Reclamação trabalhista",
                                     area="trabalhista", tribunal="TRT2", orgao="11ª Vara do Trabalho",
                                     valor_causa=95000, responsavel=user)
        p3 = Processo.objects.create(numero=cnj(42, 2026, "826", "0114"), cliente=padaria, polo_cliente="passivo",
                                     parte_contraria="Fornecedora de Farinhas S.A.", titulo="Ação de cobrança",
                                     tribunal="TJSP", orgao="2ª Vara Cível", comarca="Campinas", responsavel=user)
        Andamento.objects.create(processo=p1, data=hoje - timedelta(days=30), descricao="Petição inicial distribuída.")
        Andamento.objects.create(processo=p1, data=hoje - timedelta(days=12), descricao="Citação do réu expedida.")

        oab = OABMonitorada.objects.create(numero="123456", uf="SP", advogado="Dr. Exemplo", usuario=user)
        for dias, proc, tipo, texto in [
            (1, p1, "Intimação", "Fica a parte autora intimada para manifestar-se sobre a contestação no prazo de "
                                 "15 (quinze) dias."),
            (2, p2, "Intimação", "Designada audiência de instrução para o dia indicado. Intimem-se as partes."),
            (3, p3, "Citação", "Cite-se a ré para, querendo, contestar a ação no prazo legal."),
            (1, None, "Intimação", "Intimem-se as partes da sentença proferida nos autos."),
        ]:
            registrar(Publicacao(origem=Publicacao.MANUAL, oab=oab, data_disponibilizacao=hoje - timedelta(days=dias),
                                 tribunal=proc.tribunal if proc else "TJSP", orgao=proc.orgao if proc else "1ª Vara",
                                 tipo=tipo, texto=texto,
                                 numero_processo=proc.numero if proc else cnj(777, 2023)))

        Compromisso.objects.create(titulo="Réplica à contestação", data=hoje + timedelta(days=3), processo=p1,
                                   responsavel=user)
        Compromisso.objects.create(tipo=Compromisso.AUDIENCIA, titulo="Audiência de instrução",
                                   data=hoje + timedelta(days=6), hora="14:00", local="Sala 3 / Zoom", processo=p2,
                                   responsavel=user)
        Compromisso.objects.create(titulo="Contestação", data=hoje - timedelta(days=1), processo=p3, responsavel=user)
        Compromisso.objects.create(tipo=Compromisso.REUNIAO, titulo="Reunião com cliente", data=hoje, hora="10:30",
                                   cliente=maria, responsavel=user)

        for n in range(3):
            Lancamento.objects.create(descricao="Honorários contratuais", valor=1500, cliente=maria, processo=p1,
                                      vencimento=hoje + timedelta(days=30 * n - 20), pago=n == 0, parcela=f"{n + 1}/3")
        Lancamento.objects.create(descricao="Honorários iniciais", valor=3000, cliente=padaria, processo=p3,
                                  vencimento=hoje - timedelta(days=5))
        Lancamento.objects.create(tipo=Lancamento.DESPESA, categoria="custas", descricao="Custas iniciais",
                                  valor=380.50, processo=p3, vencimento=hoje, pago=True)
        self.stdout.write(self.style.SUCCESS("Dados de demonstração criados."))
