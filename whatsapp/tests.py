import hashlib
import hmac
import json
import shutil
import tempfile
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente

from . import api, bot
from .models import Conversa, Mensagem, Solicitacao, chave_telefone

SEGREDO = "segredo-de-teste"
MEDIA = tempfile.mkdtemp()


def assinar(corpo):
    return "sha256=" + hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()


def aviso(*mensagens, nome="Maria"):
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "5511987654321", "profile": {"name": nome}}],
        "messages": list(mensagens),
    }}]}]}


def texto(corpo, wa_id="wamid.1"):
    return {"from": "5511987654321", "id": wa_id, "timestamp": "1762950000", "type": "text", "text": {"body": corpo}}


def bloco_texto(t):
    return SimpleNamespace(type="text", text=t)


def resposta(stop_reason, *blocos):
    return SimpleNamespace(stop_reason=stop_reason, stop_details=None, content=list(blocos))


@override_settings(
    WHATSAPP_TOKEN="token", WHATSAPP_PHONE_NUMBER_ID="123", WHATSAPP_VERIFY_TOKEN="verifica",
    WHATSAPP_APP_SECRET=SEGREDO, WHATSAPP_RESPONDER_EM_SEGUNDO_PLANO=False, MEDIA_ROOT=MEDIA,
)
class WebhookTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def postar(self, payload, assinatura=None):
        corpo = json.dumps(payload).encode()
        return self.client.post(reverse("whatsapp:webhook"), corpo, content_type="application/json",
                                HTTP_X_HUB_SIGNATURE_256=assinatura or assinar(corpo))

    def test_verificacao_da_meta(self):
        url = reverse("whatsapp:webhook")
        ok = self.client.get(url, {"hub.mode": "subscribe", "hub.verify_token": "verifica", "hub.challenge": "42"})
        self.assertEqual(ok.content, b"42")
        errado = self.client.get(url, {"hub.mode": "subscribe", "hub.verify_token": "outro", "hub.challenge": "42"})
        self.assertEqual(errado.status_code, 403)

    def test_assinatura_invalida(self):
        self.assertEqual(self.postar(aviso(texto("oi")), assinatura="sha256=errada").status_code, 403)
        self.assertFalse(Mensagem.objects.exists())

    @mock.patch("whatsapp.api.enviar_texto", return_value="wamid.resposta")
    @mock.patch("whatsapp.bot.gerar_resposta", return_value="Olá! Sou o assistente virtual.")
    def test_recebe_responde_e_vincula_cliente(self, gerar, enviar):
        cliente = Cliente.objects.create(nome="Maria da Silva", celular="(11) 98765-4321")
        self.assertEqual(self.postar(aviso(texto("Bom dia"))).status_code, 200)

        conversa = Conversa.objects.get()
        self.assertEqual(conversa.cliente, cliente)
        self.assertEqual(conversa.nome, "Maria")
        enviar.assert_called_once_with("5511987654321", "Olá! Sou o assistente virtual.")
        self.assertEqual(list(conversa.mensagens.values_list("autor", flat=True)), ["contato", "robo"])

        # O WhatsApp pode reenviar o mesmo aviso: não grava nem responde de novo.
        self.postar(aviso(texto("Bom dia")))
        self.assertEqual(Mensagem.objects.count(), 2)
        self.assertEqual(enviar.call_count, 1)

    @mock.patch("whatsapp.api.enviar_texto")
    @mock.patch("whatsapp.bot.gerar_resposta")
    def test_conversa_com_a_equipe_nao_tem_resposta_automatica(self, gerar, enviar):
        Conversa.objects.create(telefone="5511987654321", bot_pausado=True)
        self.postar(aviso(texto("Oi")))
        gerar.assert_not_called()
        enviar.assert_not_called()

    @mock.patch("whatsapp.api.enviar_texto", return_value="wamid.r")
    @mock.patch("whatsapp.bot.gerar_resposta", side_effect=RuntimeError("API fora do ar"))
    def test_erro_da_ia_passa_para_equipe(self, gerar, enviar):
        self.postar(aviso(texto("Oi")))
        conversa = Conversa.objects.get()
        self.assertTrue(conversa.bot_pausado)
        self.assertTrue(conversa.solicitacoes.filter(tipo=Solicitacao.ATENDENTE).exists())
        enviar.assert_called_once_with("5511987654321", bot.RESPOSTA_ERRO)

    @mock.patch("whatsapp.api.enviar_texto", return_value="wamid.r")
    @mock.patch("whatsapp.bot.gerar_resposta", return_value="Recebi, obrigado!")
    @mock.patch("whatsapp.api.baixar_midia", return_value=(b"%PDF-1.4", "application/pdf"))
    def test_documento_recebido_fica_salvo(self, baixar, gerar, enviar):
        doc = {"from": "5511987654321", "id": "wamid.doc", "timestamp": "1762950000", "type": "document",
               "document": {"id": "mid1", "filename": "RG Maria.pdf", "mime_type": "application/pdf",
                            "caption": "meu RG"}}
        self.postar(aviso(doc))
        m = Mensagem.objects.get(wa_id="wamid.doc")
        self.assertEqual(m.nome_arquivo, "RG Maria.pdf")
        self.assertEqual(m.texto, "meu RG")
        self.assertEqual(m.arquivo.read(), b"%PDF-1.4")

        url = reverse("whatsapp:arquivo", args=[m.pk])
        self.assertEqual(self.client.get(url).status_code, 302)  # sem login, vai para a tela de entrar
        self.client.force_login(get_user_model().objects.create_user("adv", password="x"))
        self.assertEqual(self.client.get(url).status_code, 200)


class FakeClaude:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        return self.respostas.pop(0)


class RoboTest(TestCase):
    def setUp(self):
        self.conversa = Conversa.objects.create(telefone="5511987654321", nome="João")

    def entrada(self, t):
        return Mensagem.objects.create(conversa=self.conversa, direcao="entrada", autor="contato", texto=t)

    def test_historico_comeca_pelo_contato_e_junta_mensagens_seguidas(self):
        Mensagem.objects.create(conversa=self.conversa, direcao="saida", autor="equipe", texto="Bom dia")
        self.entrada("Oi")
        self.entrada("Quero marcar uma consulta")
        h = bot.historico(self.conversa)
        self.assertEqual(h, [{"role": "user", "content": "Oi\n\nQuero marcar uma consulta"}])

    def test_agendamento_pela_ferramenta(self):
        self.entrada("Sou João Souza, quero marcar sobre aposentadoria, terça de manhã")
        uso = SimpleNamespace(type="tool_use", id="t1", name="registrar_pedido_de_agendamento", input={
            "nome": "João Souza", "assunto": "aposentadoria", "preferencia": "terça de manhã",
            "modalidade": "presencial", "observacoes": "",
        })
        fake = FakeClaude([resposta("tool_use", uso), resposta("end_turn", bloco_texto("Pedido anotado!"))])
        with mock.patch("whatsapp.bot._cliente_api", return_value=fake):
            self.assertEqual(bot.gerar_resposta(self.conversa), "Pedido anotado!")

        s = Solicitacao.objects.get()
        self.assertEqual(s.tipo, Solicitacao.AGENDAMENTO)
        self.assertIn("Preferência: terça de manhã", s.detalhes)
        segunda = fake.chamadas[1]["messages"]
        self.assertEqual(segunda[-1]["content"][0]["tool_use_id"], "t1")
        self.assertEqual(segunda[1]["role"], "system")  # contexto da conversa depois da mensagem do contato

    def test_transferir_pausa_o_robo(self):
        self.entrada("Meu filho foi preso agora")
        uso = SimpleNamespace(type="tool_use", id="t1", name="transferir_para_equipe",
                              input={"motivo": "Prisão em flagrante", "urgente": True})
        fake = FakeClaude([resposta("tool_use", uso), resposta("end_turn", bloco_texto("Já avisei a equipe."))])
        with mock.patch("whatsapp.bot._cliente_api", return_value=fake):
            bot.gerar_resposta(self.conversa)
        self.conversa.refresh_from_db()
        self.assertTrue(self.conversa.bot_pausado)
        self.assertTrue(Solicitacao.objects.get().resumo.startswith("URGENTE"))

    def test_recusa_passa_para_equipe(self):
        self.entrada("…")
        fake = FakeClaude([resposta("refusal")])
        with mock.patch("whatsapp.bot._cliente_api", return_value=fake):
            self.assertEqual(bot.gerar_resposta(self.conversa), bot.RESPOSTA_ERRO)
        self.conversa.refresh_from_db()
        self.assertTrue(self.conversa.bot_pausado)


@override_settings(WHATSAPP_TOKEN="token", WHATSAPP_PHONE_NUMBER_ID="123")
class TelasTest(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("adv", password="x"))
        self.conversa = Conversa.objects.create(telefone="5511987654321", nome="Ana", nao_lida=True)
        Mensagem.objects.create(conversa=self.conversa, direcao="entrada", autor="contato", texto="Olá")

    def test_telas_abrem(self):
        for url in (reverse("whatsapp:lista"), reverse("whatsapp:solicitacoes"), reverse("whatsapp:configuracao"),
                    self.conversa.get_absolute_url()):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.conversa.refresh_from_db()
        self.assertFalse(self.conversa.nao_lida)

    @mock.patch("whatsapp.api.enviar_texto", return_value="wamid.x")
    def test_resposta_da_equipe_pausa_o_robo(self, enviar):
        self.client.post(reverse("whatsapp:responder", args=[self.conversa.pk]), {"texto": "Aqui é a Dra. Paula"})
        enviar.assert_called_once_with("5511987654321", "Aqui é a Dra. Paula")
        self.conversa.refresh_from_db()
        self.assertTrue(self.conversa.bot_pausado)
        self.assertEqual(self.conversa.mensagens.last().autor, Mensagem.EQUIPE)

    def test_devolver_ao_robo_resolve_pedido_de_atendente(self):
        bot.transferir(self.conversa, "quer falar com advogado")
        self.client.post(reverse("whatsapp:alternar_robo", args=[self.conversa.pk]))
        self.conversa.refresh_from_db()
        self.assertFalse(self.conversa.bot_pausado)
        self.assertFalse(Solicitacao.objects.filter(resolvida=False).exists())


class UtilTest(TestCase):
    def test_chave_telefone(self):
        self.assertEqual(chave_telefone("5511987654321"), chave_telefone("(11) 98765-4321"))
        self.assertEqual(chave_telefone("551187654321"), chave_telefone("11 98765-4321"))  # sem o nono dígito
        self.assertEqual(chave_telefone("123"), "")

    def test_dividir_texto(self):
        partes = api.dividir_texto(("palavra " * 1000).strip(), limite=100)
        self.assertTrue(all(len(p) <= 100 for p in partes))
        self.assertEqual(" ".join(partes), ("palavra " * 1000).strip())
