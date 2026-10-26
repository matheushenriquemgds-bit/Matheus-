import calendar
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from core.forms import DataInput, FormBase, HoraInput
from core.models import Feriado
from core.utils import eh_dia_util
from core.views import Criar, Editar, Excluir, Lista, voltar_para

from .models import Compromisso


class CompromissoForm(FormBase):
    class Meta:
        model = Compromisso
        fields = ["tipo", "titulo", "data", "hora", "local", "processo", "cliente", "responsavel", "descricao",
                  "concluido"]
        widgets = {"data": DataInput(), "hora": HoraInput(), "descricao": forms.Textarea()}

    def clean_data(self):
        data = self.cleaned_data["data"]
        if self.cleaned_data.get("tipo") == Compromisso.PRAZO and not eh_dia_util(data, Feriado.datas()):
            self.aviso = f"Atenção: {data:%d/%m/%Y} não é dia útil."
        return data


class CompromissoLista(Lista):
    model = Compromisso
    campos_busca = ("titulo", "descricao", "processo__numero", "cliente__nome")
    filtros = ("tipo", "responsavel")

    def get_queryset(self):
        qs = super().get_queryset().select_related("processo", "cliente", "responsavel")
        hoje = timezone.localdate()
        status = self.request.GET.get("status", "pendentes")
        if status == "pendentes":
            qs = qs.filter(concluido=False)
        elif status == "atrasados":
            qs = qs.filter(concluido=False, data__lt=hoje)
        elif status == "concluidos":
            qs = qs.filter(concluido=True).order_by("-data")
        if self.request.GET.get("meus"):
            qs = qs.filter(responsavel=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(status=self.request.GET.get("status", "pendentes"), tipos=Compromisso.TIPOS,
                   usuarios=get_user_model().objects.filter(is_active=True))
        return ctx


class Calendario(TemplateView):
    template_name = "agenda/calendario.html"

    def get_context_data(self, **kwargs):
        hoje = timezone.localdate()
        try:
            ano = int(self.request.GET.get("ano", hoje.year))
            mes = int(self.request.GET.get("mes", hoje.month))
            date(ano, mes, 1)
        except ValueError:
            ano, mes = hoje.year, hoje.month
        semanas = calendar.Calendar(firstweekday=6).monthdatescalendar(ano, mes)
        eventos = {}
        for c in Compromisso.objects.filter(data__range=(semanas[0][0], semanas[-1][-1])).select_related("processo"):
            eventos.setdefault(c.data, []).append(c)
        anterior = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
        proximo = (ano, mes + 1) if mes < 12 else (ano + 1, 1)
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            hoje=hoje,
            mes_atual=date(ano, mes, 1),
            semanas=[[(d, eventos.get(d, []), d.month == mes) for d in semana] for semana in semanas],
            anterior=anterior,
            proximo=proximo,
        )
        return ctx


class AvisoMixin:
    def form_valid(self, form):
        resposta = super().form_valid(form)
        if getattr(form, "aviso", None):
            messages.warning(self.request, form.aviso)
        return resposta

    def get_success_url(self):
        return voltar_para(self.request, reverse_lazy("agenda:lista"))


class CompromissoCriar(AvisoMixin, Criar):
    model = Compromisso
    form_class = CompromissoForm
    mensagem = "Compromisso agendado."

    def get_initial(self):
        inicial = super().get_initial()
        inicial["responsavel"] = self.request.user
        for campo in ("processo", "cliente", "tipo", "data"):
            if self.request.GET.get(campo):
                inicial[campo] = self.request.GET[campo]
        return inicial


class CompromissoEditar(AvisoMixin, Editar):
    model = Compromisso
    form_class = CompromissoForm
    mensagem = "Compromisso atualizado."


class CompromissoExcluir(Excluir):
    model = Compromisso
    success_url = reverse_lazy("agenda:lista")


@require_POST
def concluir(request, pk):
    c = get_object_or_404(Compromisso, pk=pk)
    c.concluido = not c.concluido
    c.save()
    messages.success(request, "Compromisso concluído." if c.concluido else "Compromisso reaberto.")
    return redirect(voltar_para(request, "agenda:lista"))
