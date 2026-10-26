"""Utilidades jurídicas: número CNJ e contagem de prazos em dias úteis."""

import re
from datetime import date, timedelta
from functools import lru_cache

CNJ_RE = re.compile(r"^(\d{7})(\d{2})(\d{4})(\d)(\d{2})(\d{4})$")


def so_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def formatar_cnj(numero):
    """Formata 20 dígitos como NNNNNNN-DD.AAAA.J.TR.OOOO; outros valores voltam como vieram."""
    m = CNJ_RE.match(so_digitos(numero))
    if not m:
        return numero
    return "{}-{}.{}.{}.{}.{}".format(*m.groups())


def digito_verificador_cnj(numero):
    """Calcula o DV (módulo 97, Resolução CNJ 65/2008) a partir dos 20 dígitos."""
    m = CNJ_RE.match(so_digitos(numero))
    if not m:
        return None
    n, _, a, j, tr, o = m.groups()
    return 98 - (int(n + a + j + tr + o + "00") % 97)


def cnj_valido(numero):
    m = CNJ_RE.match(so_digitos(numero))
    return bool(m) and int(m.group(2)) == digito_verificador_cnj(numero)


def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    dl = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * dl) // 451
    mes, dia = divmod(h + dl - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


@lru_cache(maxsize=64)
def feriados_nacionais(ano):
    """Feriados nacionais e pontos facultativos forenses de abrangência nacional."""
    p = pascoa(ano)
    fixos = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]
    moveis = [
        p - timedelta(days=48),  # segunda de Carnaval
        p - timedelta(days=47),  # terça de Carnaval
        p - timedelta(days=2),  # Sexta-feira Santa
        p + timedelta(days=60),  # Corpus Christi
    ]
    return frozenset([date(ano, m, d) for m, d in fixos] + moveis)


def em_recesso(dia):
    """Recesso forense: prazos suspensos de 20/12 a 20/01 (CPC, art. 220)."""
    return (dia.month == 12 and dia.day >= 20) or (dia.month == 1 and dia.day <= 20)


def eh_dia_util(dia, feriados_extras=frozenset(), considerar_recesso=True):
    if dia.weekday() >= 5:
        return False
    if dia in feriados_nacionais(dia.year) or dia in feriados_extras:
        return False
    if considerar_recesso and em_recesso(dia):
        return False
    return True


def proximo_dia_util(dia, **kwargs):
    """Primeiro dia útil estritamente posterior a `dia`."""
    dia += timedelta(days=1)
    while not eh_dia_util(dia, **kwargs):
        dia += timedelta(days=1)
    return dia


def somar_dias_uteis(inicio, dias, **kwargs):
    """Data final de um prazo de `dias` dias úteis, excluindo o dia do início (CPC, art. 224)."""
    data = inicio
    for _ in range(dias):
        data = proximo_dia_util(data, **kwargs)
    return data


def vencimento_por_disponibilizacao(disponibilizacao, dias, **kwargs):
    """Vencimento de prazo contado a partir de publicação no Diário eletrônico.

    Considera-se publicada no primeiro dia útil seguinte à disponibilização e o
    prazo começa a correr no primeiro dia útil seguinte à publicação
    (Lei 11.419/2006, art. 4º, §§ 3º e 4º).
    """
    publicacao = proximo_dia_util(disponibilizacao, **kwargs)
    return somar_dias_uteis(publicacao, dias, **kwargs)
