"""Comunicação com a WhatsApp Cloud API (Meta).

Documentação: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import hashlib
import hmac
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

log = logging.getLogger(__name__)

LIMITE_TEXTO = 4096  # tamanho máximo de uma mensagem de texto no WhatsApp


class ErroWhatsApp(Exception):
    pass


def configurado():
    return bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)


def _url(caminho):
    return f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{caminho}"


def _requisicao(url, dados=None, timeout=30, json_resposta=True):
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
    corpo = None
    if dados is not None:
        corpo = json.dumps(dados).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=corpo, headers=headers, method="POST" if corpo else "GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            conteudo = resp.read()
            if not json_resposta:
                return conteudo, resp.headers.get("Content-Type", "")
            return json.loads(conteudo.decode("utf-8"))
    except HTTPError as e:
        try:
            detalhe = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except ValueError:
            detalhe = ""
        raise ErroWhatsApp(f"O WhatsApp recusou a requisição (erro {e.code}). {detalhe}".strip()) from e
    except (URLError, TimeoutError) as e:
        raise ErroWhatsApp(f"Não foi possível conectar ao WhatsApp: {getattr(e, 'reason', e)}") from e


def dividir_texto(texto, limite=LIMITE_TEXTO):
    """Quebra textos longos em partes que caibam numa mensagem, preferindo quebras de parágrafo."""
    partes = []
    texto = texto.strip()
    while len(texto) > limite:
        corte = texto.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = texto.rfind(" ", 0, limite)
        if corte <= 0:
            corte = limite
        partes.append(texto[:corte].strip())
        texto = texto[corte:].strip()
    if texto:
        partes.append(texto)
    return partes


def enviar_texto(telefone, texto):
    """Envia uma mensagem de texto e devolve o ID do WhatsApp da última parte enviada."""
    if not configurado():
        raise ErroWhatsApp("WhatsApp não configurado: defina WHATSAPP_TOKEN e WHATSAPP_PHONE_NUMBER_ID.")
    wa_id = None
    for parte in dividir_texto(texto):
        resposta = _requisicao(_url(f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"), {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone,
            "type": "text",
            "text": {"preview_url": False, "body": parte},
        })
        wa_id = (resposta.get("messages") or [{}])[0].get("id")
    return wa_id


def baixar_midia(media_id):
    """Baixa um arquivo recebido. Devolve (conteúdo, content-type)."""
    info = _requisicao(_url(media_id))
    url = info.get("url")
    if not url:
        raise ErroWhatsApp("O WhatsApp não informou o endereço do arquivo.")
    return _requisicao(url, timeout=60, json_resposta=False)


def assinatura_valida(corpo, cabecalho):
    """Confere o cabeçalho X-Hub-Signature-256 com o App Secret do aplicativo da Meta."""
    segredo = settings.WHATSAPP_APP_SECRET
    if not segredo:
        return False
    esperado = "sha256=" + hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho or "")
