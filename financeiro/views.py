import calendar

from django import forms
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.forms import DataInput, FormBase
from core.views import Criar, Editar, Excluir, Lista, voltar_para

from .models import Lancamento


class LancamentoForm(FormBase):
    parcelas = forms.IntegerField(
        label="Repetir em parcelas mensais", min_value=1, max_value=120, initial=1, required=False,
        help_text="Só no cadastro. Ex.: 10 gera 10 lançamentos mensais com o mesmo valor.",
    )

    class Meta:
        model = Lancamento
        fields = ["tipo", "categoria", "descricao", "valor", "vencimento", "parcelas", "cliente", "processo",
                  "pago", "data_pagamento", "forma_pagamento", "observacoes"]
        widgets = {"vencimento": DataInput(), "data_pagamento": DataInput(), "observacoes": forms.Textarea()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["parcelas"]


def somar_meses(data, meses):
    mes = data.month - 1 + meses
    ano, mes = data.year + mes // 12, mes % 12 + 1
    return data.replace(year=ano, month=mes, day=min(data.day, calendar.monthrange(ano, mes)[1]))


class LancamentoLista(Lista):
    model = Lancamento
    campos_busca = ("descricao", "cliente__nome", "processo__numero")
    filtros = ("tipo", "categoria", "cliente")

    def get_queryset(self):
        qs = super().get_queryset().select_related("cliente", "processo")
        hoje = timezone.localdate()
        status = self.request.GET.get("status", "abertos")
        if status == "abertos":
            qs = qs.filter(pago=False)
        elif status == "vencidos":
            qs = qs.filter(pago=False, vencimento__lt=hoje)
        elif status == "pagos":
            qs = qs.filter(pago=True).order_by("-data_pagamento")
        de, ate = self.request.GET.get("de"), self.request.GET.get("ate")
        if de:
            qs = qs.filter(vencimento__gte=de)
        if ate:
            qs = qs.filter(vencimento__lte=ate)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.object_list
        soma = lambda cond: qs.filter(cond).aggregate(t=Sum("valor"))["t"] or 0  # noqa: E731
        receitas = soma(Q(tipo=Lancamento.RECEITA))
        despesas = soma(Q(tipo=Lancamento.DESPESA))
        hoje = timezone.localdate()
        inicio_mes = hoje.replace(day=1)
        fim_mes = somar_meses(inicio_mes, 1)
        recebido_mes = Lancamento.objects.filter(
            tipo=Lancamento.RECEITA, pago=True, data_pagamento__gte=inicio_mes, data_pagamento__lt=fim_mes
        ).aggregate(t=Sum("valor"))["t"] or 0
        ctx.update(
            status=self.request.GET.get("status", "abertos"),
            categorias=Lancamento.CATEGORIAS,
            receitas=receitas,
            despesas=despesas,
            saldo=receitas - despesas,
            recebido_mes=recebido_mes,
        )
        return ctx


class LancamentoCriar(Criar):
    model = Lancamento
    form_class = LancamentoForm
    mensagem = "Lançamento registrado."

    def get_initial(self):
        inicial = super().get_initial()
        for campo in ("cliente", "processo", "tipo"):
            if self.request.GET.get(campo):
                inicial[campo] = self.request.GET[campo]
        return inicial

    def form_valid(self, form):
        parcelas = form.cleaned_data.get("parcelas") or 1
        resposta = super().form_valid(form)
        if parcelas > 1:
            base = self.object
            base.parcela = f"1/{parcelas}"
            base.save()
            for n in range(1, parcelas):
                Lancamento.objects.create(
                    tipo=base.tipo, categoria=base.categoria, descricao=base.descricao, valor=base.valor,
                    vencimento=somar_meses(base.vencimento, n), cliente=base.cliente, processo=base.processo,
                    forma_pagamento=base.forma_pagamento, parcela=f"{n + 1}/{parcelas}",
                )
        return resposta

    def get_success_url(self):
        return voltar_para(self.request, reverse_lazy("financeiro:lista"))


class LancamentoEditar(Editar):
    model = Lancamento
    form_class = LancamentoForm
    mensagem = "Lançamento atualizado."

    def get_success_url(self):
        return voltar_para(self.request, reverse_lazy("financeiro:lista"))


class LancamentoExcluir(Excluir):
    model = Lancamento
    success_url = reverse_lazy("financeiro:lista")


@require_POST
def alternar_pago(request, pk):
    lanc = get_object_or_404(Lancamento, pk=pk)
    lanc.pago = not lanc.pago
    lanc.save()
    messages.success(request, "Pagamento registrado." if lanc.pago else "Pagamento desfeito.")
    return redirect(voltar_para(request, "financeiro:lista"))
