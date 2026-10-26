from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from agenda.models import Compromisso
from clientes.models import Cliente
from processos.models import Andamento, Processo

from . import servicos
from .models import OABMonitorada, Publicacao

ITEM = {
    "id": 987654,
    "data_disponibilizacao": "2026-10-23",
    "siglaTribunal": "TJSP",
    "tipoComunicacao": "Intimação",
    "nomeOrgao": "1ª Vara Cível do Foro Central",
    "texto": "<p>Fica a parte autora intimada para se manifestar em 15 dias.</p>",
    "numero_processo": "00012343720258260100",
    "numeroprocessocommascara": "0001234-37.2025.8.26.0100",
    "link": "https://comunicaapi.pje.jus.br/api/v1/comunicacao/abc/certidao",
    "destinatarios": [{"nome": "MARIA DA SILVA", "polo": "A"}],
    "destinatarioadvogados": [{"advogado": {"nome": "JOÃO ADVOGADO", "numero_oab": "123456", "uf_oab": "SP"}}],
}


def resposta(itens):
    return {"status": "success", "count": len(itens), "items": itens}


class ImportacaoTest(TestCase):
    def setUp(self):
        self.oab = OABMonitorada.objects.create(numero="123456", uf="SP", advogado="João Advogado")
        self.cliente = Cliente.objects.create(nome="Maria da Silva")
        self.processo = Processo.objects.create(numero="0001234-37.2025.8.26.0100", cliente=self.cliente)

    def test_normalizar(self):
        campos = servicos.normalizar(ITEM)
        self.assertEqual(campos["id_externo"], "djen:987654")
        self.assertEqual(campos["data_disponibilizacao"], date(2026, 10, 23))
        self.assertEqual(campos["texto"], "Fica a parte autora intimada para se manifestar em 15 dias.")
        self.assertIn("OAB/SP 123456", campos["advogados"])

    @mock.patch.object(servicos, "_get")
    def test_importa_vincula_e_nao_duplica(self, get):
        get.return_value = resposta([ITEM])
        novas = servicos.buscar_oab(self.oab, date(2026, 10, 20), date(2026, 10, 23))
        self.assertEqual(novas, 1)
        pub = Publicacao.objects.get()
        self.assertEqual(pub.processo, self.processo)
        self.assertEqual(Andamento.objects.filter(processo=self.processo, publicacao=pub).count(), 1)
        params = get.call_args[0][0]
        self.assertEqual((params["numeroOab"], params["ufOab"]), ("123456", "SP"))

        # Segunda busca com o mesmo item não duplica
        self.assertEqual(servicos.buscar_oab(self.oab, date(2026, 10, 20), date(2026, 10, 23)), 0)
        self.assertEqual(Publicacao.objects.count(), 1)
        self.oab.refresh_from_db()
        self.assertEqual(self.oab.ultima_busca, date(2026, 10, 23))

    @mock.patch.object(servicos, "_get")
    def test_paginacao(self, get):
        pagina1 = [{**ITEM, "id": i} for i in range(1, servicos.ITENS_POR_PAGINA + 1)]
        get.side_effect = [
            {"count": servicos.ITENS_POR_PAGINA + 1, "items": pagina1},
            {"count": servicos.ITENS_POR_PAGINA + 1, "items": [{**ITEM, "id": "ultimo"}]},
        ]
        self.assertEqual(servicos.buscar_oab(self.oab, date(2026, 10, 23), date(2026, 10, 23)), 101)
        self.assertEqual(get.call_count, 2)

    @mock.patch.object(servicos, "_get", side_effect=servicos.ErroBusca("fora do ar"))
    def test_erro_reportado(self, _):
        total, erros = servicos.buscar_todas(date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(total, 0)
        self.assertEqual(len(erros), 1)

    def test_processo_cadastrado_depois_recebe_publicacao(self):
        pub = servicos.registrar(Publicacao(data_disponibilizacao=date(2026, 10, 23), texto="x",
                                            numero_processo="0009999-94.2025.8.26.0100"))
        self.assertIsNone(pub.processo)
        user = get_user_model().objects.create_user("adv")
        self.client.force_login(user)
        self.client.post(reverse("processos:criar"), {
            "numero": "0009999-94.2025.8.26.0100", "cliente": self.cliente.pk, "polo_cliente": "ativo",
            "area": "civel", "situacao": "ativo",
        })
        pub.refresh_from_db()
        self.assertEqual(pub.processo.numero, "0009999-94.2025.8.26.0100")


class TelasPublicacaoTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("adv")
        self.client.force_login(self.user)
        cliente = Cliente.objects.create(nome="Maria")
        self.processo = Processo.objects.create(numero="0001234-37.2025.8.26.0100", cliente=cliente)
        self.pub = servicos.registrar(Publicacao(
            data_disponibilizacao=date(2026, 10, 23), texto="Intimação", numero_processo="00012343720258260100"))

    def test_detalhe_e_prazo(self):
        resp = self.client.get(self.pub.get_absolute_url())
        self.assertContains(resp, "03/11/2026")  # simulação de 5 dias úteis
        self.client.post(reverse("publicacoes:criar_prazo", args=[self.pub.pk]), {
            "titulo": "Manifestação", "dias": 5, "contagem": "uteis", "responsavel": self.user.pk,
        })
        prazo = Compromisso.objects.get()
        self.assertEqual((prazo.data, prazo.processo, prazo.publicacao), (date(2026, 11, 3), self.processo, self.pub))
        self.pub.refresh_from_db()
        self.assertTrue(self.pub.lida)

    def test_prazo_corrido_prorroga_para_dia_util(self):
        # 23/10 + 1 + 7 = 31/10 (sábado) -> 03/11 (02/11 é feriado)
        self.client.post(reverse("publicacoes:criar_prazo", args=[self.pub.pk]),
                         {"titulo": "X", "dias": 7, "contagem": "corridos"})
        self.assertEqual(Compromisso.objects.get().data, date(2026, 11, 3))

    def test_marcar_varias(self):
        self.client.post(reverse("publicacoes:marcar_varias"), {"ids": [self.pub.pk]})
        self.pub.refresh_from_db()
        self.assertTrue(self.pub.lida)
        self.assertEqual(self.pub.lida_por, self.user)

    def test_lista_filtra_nao_lidas(self):
        self.assertContains(self.client.get(reverse("publicacoes:lista")), "0001234-37.2025.8.26.0100")
        Publicacao.objects.update(lida=True)
        self.assertNotContains(self.client.get(reverse("publicacoes:lista")), "0001234-37.2025.8.26.0100")
