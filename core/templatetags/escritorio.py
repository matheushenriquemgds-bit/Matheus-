from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def reais(valor):
    """Formata como moeda brasileira: R$ 1.234,56."""
    if valor in (None, ""):
        return "—"
    valor = Decimal(valor).quantize(Decimal("0.01"))
    inteiro, centavos = f"{abs(valor):,.2f}".split(".")
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {inteiro.replace(',', '.')},{centavos}"


@register.simple_tag
def url_ordem(querystring, page):
    return f"?{querystring + '&' if querystring else ''}page={page}"
