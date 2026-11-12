"""Recebimento das mensagens do WhatsApp e envio das respostas."""

import logging
import mimetypes
import threading
from collections import defaultdict
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from . import api, bot
from .models import Configuracao, Conversa, Mensagem

log = logging.getLogger(__name__)

TIPOS_COM_ARQUIVO = ("document", "image", "audio", "video", "sticker")

_travas = defaultdict(threading.Lock)
_trava_global = threading.Lock()


def _trava(conversa_id):
    with _trava_global:
        return _travas[conversa_id]


def _data(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc)
    except (TypeError, ValueError):
        return timezone.now()


def _texto_e_tipo(msg):
    tipo = msg.get("type", "")
    if tipo == "text":
        return msg.get("text", {}).get("body", ""), tipo
    if tipo in TIPOS_COM_ARQUIVO:
        return msg.get(tipo, {}).get("caption", ""), tipo
    if tipo == "button":
        return msg.get("button", {}).get("text", ""), "text"
    if tipo == "interactive":
        inter = msg.get("interactive", {})
        escolha = inter.get("button_reply") or inter.get("list_reply") or {}
        return escolha.get("title", ""), "text"
    if tipo == "location":
        loc = msg.get("location", {})
        return f"[Localização: {loc.get('name') or ''} {loc.get('address') or ''}]".strip(), tipo
    if tipo == "contacts":
        return "[Cartão de contato]", tipo
    return "", tipo or "desconhecido"


def _salvar_arquivo(mensagem, msg):
    dados = msg.get(mensagem.tipo, {})
    media_id = dados.get("id")
    if not media_id:
        return
    try:
        conteudo, content_type = api.baixar_midia(media_id)
    except api.ErroWhatsApp as e:
        log.warning("Não foi possível baixar o arquivo %s: %s", media_id, e)
        mensagem.erro = "Arquivo não baixado"
        mensagem.save(update_fields=["erro"])
        return
    mime = (dados.get("mime_type") or content_type or "").split(";")[0].strip()
    nome = dados.get("filename") or ""
    extensao = mimetypes.guess_extension(mime) or ""
    if not nome:
        nome = f"{mensagem.tipo}-{timezone.localtime(mensagem.criada_em):%Y%m%d-%H%M%S}{extensao}"
    mensagem.nome_arquivo = nome[:200]
    mensagem.arquivo.save(get_valid_filename(nome)[:100] or f"arquivo{extensao}", ContentFile(conteudo), save=False)
    mensagem.save(update_fields=["arquivo", "nome_arquivo"])


def registrar_entrada(msg, nomes):
    """Grava uma mensagem recebida. Devolve a conversa, ou None se a mensagem já tinha sido gravada."""
    telefone = msg.get("from", "")
    if not telefone:
        return None
    texto, tipo = _texto_e_tipo(msg)
    quando = _data(msg.get("timestamp"))
    with transaction.atomic():
        conversa, criada = Conversa.objects.select_for_update().get_or_create(telefone=telefone)
        if nomes.get(telefone):
            conversa.nome = nomes[telefone][:150]
        if criada or not conversa.cliente_id:
            conversa.cliente = conversa.localizar_cliente()
        try:
            with transaction.atomic():
                mensagem = Mensagem.objects.create(
                    conversa=conversa, direcao=Mensagem.ENTRADA, autor=Mensagem.CONTATO,
                    tipo=tipo, texto=texto, wa_id=msg.get("id"), criada_em=quando,
                )
        except IntegrityError:
            return None  # o WhatsApp reenviou uma mensagem que já temos
        conversa.ultima_mensagem_em = conversa.ultima_entrada_em = quando
        conversa.nao_lida = True
        conversa.save()
    if tipo in TIPOS_COM_ARQUIVO:
        _salvar_arquivo(mensagem, msg)
    return conversa


def processar_webhook(payload):
    """Grava as mensagens de um aviso do WhatsApp e devolve os IDs das conversas a responder."""
    conversas = []
    for entrada in payload.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})
            nomes = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in valor.get("contacts", [])}
            for msg in valor.get("messages", []):
                conversa = registrar_entrada(msg, nomes)
                if conversa and conversa.pk not in conversas:
                    conversas.append(conversa.pk)
            for status in valor.get("statuses", []):
                if status.get("status") == "failed":
                    erro = (status.get("errors") or [{}])[0]
                    motivo = erro.get("message") or erro.get("title") or "Falha na entrega"
                    Mensagem.objects.filter(wa_id=status.get("id")).update(erro=motivo[:300])
    return conversas


def responder(conversa_id):
    """Gera e envia a resposta do robô, se ele estiver ligado para esta conversa."""
    with _trava(conversa_id):
        conversa = Conversa.objects.select_related("cliente").get(pk=conversa_id)
        if not Configuracao.atual().bot_ativo or conversa.bot_pausado:
            return
        ultima = conversa.mensagens.order_by("-criada_em", "-pk").first()
        if not ultima or ultima.direcao != Mensagem.ENTRADA:
            return  # já respondida (por exemplo, várias mensagens seguidas tratadas de uma vez)
        try:
            texto = bot.gerar_resposta(conversa)
        except Exception:  # noqa: BLE001 - falha da IA não pode deixar o contato sem resposta
            log.exception("Erro ao gerar resposta para a conversa %s", conversa_id)
            bot.transferir(conversa, "O robô teve um erro técnico ao responder")
            texto = bot.RESPOSTA_ERRO
        if texto:
            enviar(conversa, texto, autor=Mensagem.ROBO)


def enviar(conversa, texto, autor, usuario=None):
    """Envia um texto ao contato e grava a mensagem (com o erro, se o envio falhar)."""
    mensagem = Mensagem(conversa=conversa, direcao=Mensagem.SAIDA, autor=autor, usuario=usuario, texto=texto)
    try:
        mensagem.wa_id = api.enviar_texto(conversa.telefone, texto)
    except api.ErroWhatsApp as e:
        log.warning("Falha ao enviar para %s: %s", conversa.telefone, e)
        mensagem.erro = str(e)[:300]
    mensagem.save()
    conversa.ultima_mensagem_em = mensagem.criada_em
    conversa.save(update_fields=["ultima_mensagem_em", "atualizado_em"])
    return mensagem


def _responder_em_segundo_plano(conversa_id):
    try:
        responder(conversa_id)
    finally:
        close_old_connections()


def agendar_respostas(conversas):
    """Responde fora da requisição, porque o WhatsApp exige que o aviso seja confirmado em poucos segundos."""
    for conversa_id in conversas:
        if settings.WHATSAPP_RESPONDER_EM_SEGUNDO_PLANO:
            threading.Thread(target=_responder_em_segundo_plano, args=(conversa_id,), daemon=True).start()
        else:
            responder(conversa_id)
