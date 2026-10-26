from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from agenda.models import Compromisso
from clientes.models import Cliente
from financeiro.models import Lancamento
from processos.models import Processo

from .templatetags.escritorio import reais
from .utils import (
    cnj_valido, eh_dia_util, formatar_cnj, pascoa, somar_dias_uteis, vencimento_por_disponibilizacao,
)

CNJ = "0001234-37.2025.8.26.0100"


class UtilsTest(TestCase):
    def test_cnj(self):
        self.assertEqual(formatar_cnj("00012343720258260100"), CNJ)
        self.assertTrue(cnj_valido(CNJ))
        self.assertFalse(cnj_valido("0001234-38.2025.8.26.0100"))
        self.assertEqual(formatar_cnj("123"), "123")

    def test_pascoa_e_feriados(self):
        self.assertEqual(pascoa(2026), date(2026, 4, 5))
        self.assertFalse(eh_dia_util(date(2026, 2, 17)))  # terça de Carnaval
        self.assertFalse(eh_dia_util(date(2026, 4, 3)))  # Sexta-feira Santa
        self.assertFalse(eh_dia_util(date(2026, 11, 20)))  # Consciência Negra
        self.assertFalse(eh_dia_util(date(2026, 12, 22)))  # recesso
        self.assertTrue(eh_dia_util(date(2026, 10, 27)))

    def test_prazo_por_disponibilizacao(self):
        # Disponibilizada sex 23/10; publicada seg 26/10; conta de 27/10; 02/11 é Finados.
        self.assertEqual(vencimento_por_disponibilizacao(date(2026, 10, 23), 5), date(2026, 11, 3))
        self.assertEqual(vencimento_por_disponibilizacao(date(2026, 10, 23), 1, feriados_extras={date(2026, 10, 27)}),
                         date(2026, 10, 28))

    def test_prazo_atravessa_recesso(self):
        self.assertEqual(somar_dias_uteis(date(2026, 12, 18), 1), date(2027, 1, 21))

    def test_reais(self):
        self.assertEqual(reais(1234.5), "R$ 1.234,50")
        self.assertEqual(reais(-10), "-R$ 10,00")


class TelasTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("adv", password="senha-forte-123")
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nome="Maria da Silva", cpf_cnpj="12345678901")
        self.processo = Processo.objects.create(numero="00012343720258260100", cliente=self.cliente)
        Compromisso.objects.create(titulo="Contestação", data=date(2026, 1, 5), processo=self.processo)
        Lancamento.objects.create(descricao="Honorários", valor=1500, vencimento=date(2026, 1, 10),
                                  processo=self.processo)

    def test_login_obrigatorio(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_paginas_abrem(self):
        urls = [
            reverse("dashboard"),
            reverse("clientes:lista"), reverse("clientes:criar"), reverse("clientes:detalhe", args=[self.cliente.pk]),
            reverse("clientes:editar", args=[self.cliente.pk]),
            reverse("processos:lista"), reverse("processos:criar"),
            reverse("processos:detalhe", args=[self.processo.pk]),
            reverse("publicacoes:lista"), reverse("publicacoes:criar"), reverse("publicacoes:oabs"),
            reverse("publicacoes:oab_criar"),
            reverse("agenda:lista"), reverse("agenda:calendario"), reverse("agenda:criar"),
            reverse("financeiro:lista"), reverse("financeiro:criar"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_processo_numero_formatado_e_cliente_herdado(self):
        self.assertEqual(self.processo.numero, CNJ)
        self.assertEqual(Compromisso.objects.get().cliente, self.cliente)
        self.assertEqual(Lancamento.objects.get().cliente, self.cliente)

    def test_processo_duplicado_ou_dv_invalido(self):
        dados = {"cliente": self.cliente.pk, "polo_cliente": "ativo", "area": "civel", "situacao": "ativo"}
        resp = self.client.post(reverse("processos:criar"), {**dados, "numero": CNJ})
        self.assertContains(resp, "Já existe um processo")
        resp = self.client.post(reverse("processos:criar"), {**dados, "numero": "0001234-38.2025.8.26.0100"})
        self.assertContains(resp, "Dígito verificador inválido")

    def test_parcelamento(self):
        self.client.post(reverse("financeiro:criar"), {
            "tipo": "receita", "categoria": "honorarios_contratuais", "descricao": "Contrato", "valor": "500",
            "vencimento": "2026-01-31", "parcelas": "3", "cliente": self.cliente.pk,
        })
        venc = list(Lancamento.objects.filter(descricao="Contrato").order_by("vencimento")
                    .values_list("vencimento", "parcela"))
        self.assertEqual(venc, [(date(2026, 1, 31), "1/3"), (date(2026, 2, 28), "2/3"), (date(2026, 3, 31), "3/3")])

    def test_redirecionamento_externo_bloqueado(self):
        c = Compromisso.objects.get()
        resp = self.client.post(reverse("agenda:concluir", args=[c.pk]), {"voltar": "https://exemplo.com"})
        self.assertEqual(resp["Location"], reverse("agenda:lista"))
        c.refresh_from_db()
        self.assertTrue(c.concluido)
