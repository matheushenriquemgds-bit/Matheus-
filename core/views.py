from datetime import timedelta

from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView


def voltar_para(request, padrao):
    """URL de retorno vinda de `?voltar=`/POST, aceitando apenas endereços deste site."""
    destino = request.POST.get("voltar") or request.GET.get("voltar")
    if destino and url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
        return destino
    return padrao


class Lista(ListView):
    """ListView com busca textual (`?q=`) e filtros simples por GET."""

    paginate_by = 25
    campos_busca = ()
    filtros = ()  # nomes de campos filtráveis por igualdade via querystring

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q and self.campos_busca:
            cond = Q()
            for campo in self.campos_busca:
                cond |= Q(**{f"{campo}__icontains": q})
            qs = qs.filter(cond)
        for campo in self.filtros:
            valor = self.request.GET.get(campo)
            if valor:
                qs = qs.filter(**{campo: valor})
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class NomeModeloMixin:
    def get_context_data(self, **kwargs):
        return super().get_context_data(nome_modelo=self.model._meta.verbose_name, **kwargs)


class MensagemMixin(NomeModeloMixin):
    mensagem = "Registro salvo."

    def form_valid(self, form):
        resposta = super().form_valid(form)
        messages.success(self.request, self.mensagem)
        return resposta


class Criar(MensagemMixin, CreateView):
    template_name = "core/form.html"


class Editar(MensagemMixin, UpdateView):
    template_name = "core/form.html"


class Excluir(NomeModeloMixin, DeleteView):
    template_name = "core/confirmar_exclusao.html"

    def form_valid(self, form):
        messages.success(self.request, "Registro excluído.")
        return super().form_valid(form)


class Dashboard(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        from agenda.models import Compromisso
        from financeiro.models import Lancamento
        from processos.models import Processo
        from publicacoes.models import Publicacao

        hoje = timezone.localdate()
        pendentes = Compromisso.objects.filter(concluido=False).select_related("processo", "responsavel")
        receitas = Lancamento.objects.filter(tipo=Lancamento.RECEITA, pago=False)
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            hoje=hoje,
            atrasados=pendentes.filter(data__lt=hoje),
            proximos=pendentes.filter(data__gte=hoje, data__lte=hoje + timedelta(days=7)),
            publicacoes=Publicacao.objects.filter(lida=False).select_related("processo")[:8],
            total_nao_lidas=Publicacao.objects.filter(lida=False).count(),
            processos_ativos=Processo.objects.filter(situacao=Processo.ATIVO).count(),
            a_receber=receitas.aggregate(t=Sum("valor"))["t"] or 0,
            receber_vencido=receitas.filter(vencimento__lt=hoje).aggregate(t=Sum("valor"))["t"] or 0,
        )
        return ctx
