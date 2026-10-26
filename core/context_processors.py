from django.utils import timezone


def contadores(request):
    """Números exibidos como selos no menu lateral."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from agenda.models import Compromisso
    from publicacoes.models import Publicacao

    return {
        "menu_nao_lidas": Publicacao.objects.filter(lida=False).count(),
        "menu_atrasados": Compromisso.objects.filter(concluido=False, data__lte=timezone.localdate()).count(),
    }
