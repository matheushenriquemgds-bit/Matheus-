"""Recebimento de publicações pela API pública do CNJ (DJEN / Comunica PJe).

Documentação: https://comunicaapi.pje.jus.br/swagger/index.html
"""

import html
import json
import logging
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from processos.models import Andamento

from .models import OABMonitorada, Publicacao

log = logging.getLogger(__name__)

ITENS_POR_PAGINA = 100
JANELA_DIAS = 30  # a busca é dividida em janelas para não estourar limites da API


class ErroBusca(Exception):
    pass


def _get(params, timeout=30):
    url = f"{settings.COMUNICA_API_URL}?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "escritorio-juridico/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        raise ErroBusca(f"A API do CNJ respondeu com erro {e.code}.") from e
    except (URLError, TimeoutError) as e:
        raise ErroBusca(f"Não foi possível conectar à API do CNJ: {getattr(e, 'reason', e)}") from e
    except ValueError as e:
        raise ErroBusca("A API do CNJ devolveu uma resposta inválida.") from e


def consultar(numero_oab, uf, inicio, fim):
    """Gera os itens brutos da API para a OAB entre as datas (inclusive), com paginação."""
    pagina = 1
    while True:
        dados = _get({
            "numeroOab": numero_oab,
            "ufOab": uf,
            "dataDisponibilizacaoInicio": inicio.isoformat(),
            "dataDisponibilizacaoFim": fim.isoformat(),
            "pagina": pagina,
            "itensPorPagina": ITENS_POR_PAGINA,
        })
        itens = dados.get("items") or []
        yield from itens
        total = dados.get("count") or 0
        if len(itens) < ITENS_POR_PAGINA or pagina * ITENS_POR_PAGINA >= total:
            break
        pagina += 1


def _data(valor):
    if not valor:
        return None
    valor = str(valor)[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            continue
    return None


def _texto(valor):
    return html.unescape(strip_tags(valor or "")).strip()


def normalizar(item):
    """Converte um item da API nos campos do modelo Publicacao."""
    destinatarios = [d.get("nome", "") for d in item.get("destinatarios") or []]
    advogados = []
    for d in item.get("destinatarioadvogados") or []:
        adv = d.get("advogado") or {}
        if adv.get("nome"):
            advogados.append(f"{adv['nome']} (OAB/{adv.get('uf_oab', '')} {adv.get('numero_oab', '')})")
    return {
        "id_externo": f"djen:{item.get('id') or item.get('hash')}",
        "data_disponibilizacao": _data(item.get("data_disponibilizacao") or item.get("datadisponibilizacao")),
        "tribunal": item.get("siglaTribunal") or "",
        "orgao": item.get("nomeOrgao") or "",
        "tipo": item.get("tipoComunicacao") or item.get("tipoDocumento") or "",
        "numero_processo": item.get("numeroprocessocommascara") or item.get("numero_processo") or "",
        "texto": _texto(item.get("texto")),
        "link": item.get("link") or "",
        "destinatarios": "\n".join(filter(None, destinatarios)),
        "advogados": "\n".join(advogados),
    }


def registrar(publicacao):
    """Vincula a publicação ao processo e lança o andamento correspondente."""
    processo = publicacao.vincular_processo()
    publicacao.save()
    if processo and not Andamento.objects.filter(publicacao=publicacao).exists():
        cabecalho = " — ".join(filter(None, [publicacao.tipo, publicacao.orgao]))
        Andamento.objects.create(
            processo=processo,
            data=publicacao.data_disponibilizacao,
            descricao=f"[{cabecalho or 'Publicação'}] {publicacao.texto[:1000]}",
            origem=Andamento.PUBLICACAO,
            publicacao=publicacao,
        )
    return publicacao


def importar_itens(oab, itens):
    novas = 0
    for item in itens:
        campos = normalizar(item)
        if not campos["data_disponibilizacao"] or campos["id_externo"].endswith(":None"):
            log.warning("Item ignorado por falta de data ou identificador: %s", item)
            continue
        with transaction.atomic():
            if Publicacao.objects.filter(id_externo=campos["id_externo"]).exists():
                continue
            registrar(Publicacao(origem=Publicacao.DJEN, oab=oab, **campos))
            novas += 1
    return novas


def buscar_oab(oab, inicio=None, fim=None):
    """Busca e grava as publicações de uma OAB. Retorna a quantidade de novas."""
    hoje = timezone.localdate()
    fim = fim or hoje
    if inicio is None:
        # Revisa um dia antes da última busca para pegar disponibilizações tardias.
        inicio = (oab.ultima_busca - timedelta(days=1)) if oab.ultima_busca else (
            hoje - timedelta(days=settings.PUBLICACOES_DIAS_INICIAIS)
        )
    novas = 0
    janela = inicio
    while janela <= fim:
        fim_janela = min(janela + timedelta(days=JANELA_DIAS - 1), fim)
        novas += importar_itens(oab, consultar(oab.numero, oab.uf, janela, fim_janela))
        janela = fim_janela + timedelta(days=1)
    if not oab.ultima_busca or fim > oab.ultima_busca:
        oab.ultima_busca = fim
        oab.save(update_fields=["ultima_busca"])
    return novas


def buscar_todas(inicio=None, fim=None):
    """Busca todas as OABs ativas. Retorna (total_novas, lista_de_erros)."""
    total, erros = 0, []
    for oab in OABMonitorada.objects.filter(ativa=True):
        try:
            total += buscar_oab(oab, inicio, fim)
        except ErroBusca as e:
            erros.append(f"{oab}: {e}")
    return total, erros
