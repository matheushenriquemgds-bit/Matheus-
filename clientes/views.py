from django import forms
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DetailView

from core.forms import DataInput, FormBase
from core.views import Criar, Editar, Excluir, Lista

from .models import Cliente


class ClienteForm(FormBase):
    class Meta:
        model = Cliente
        exclude = ["criado_em", "atualizado_em"]
        widgets = {"data_nascimento": DataInput(), "observacoes": forms.Textarea()}


class ClienteLista(Lista):
    model = Cliente
    campos_busca = ("nome", "cpf_cnpj", "email", "telefone", "celular", "cidade")
    filtros = ("tipo", "ativo")

    def get_queryset(self):
        return super().get_queryset().annotate(num_processos=Count("processos"))


class ClienteDetalhe(DetailView):
    model = Cliente

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        ctx.update(
            processos=c.processos.all(),
            compromissos=c.compromissos.filter(concluido=False).select_related("processo"),
            lancamentos=c.lancamentos.all()[:20],
        )
        return ctx


class ClienteCriar(Criar):
    model = Cliente
    form_class = ClienteForm
    mensagem = "Cliente cadastrado."


class ClienteEditar(Editar):
    model = Cliente
    form_class = ClienteForm
    mensagem = "Cliente atualizado."


class ClienteExcluir(Excluir):
    model = Cliente
    success_url = reverse_lazy("clientes:lista")

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.processos.exists() or obj.lancamentos.exists():
            messages.error(request, "Este cliente tem processos ou lançamentos vinculados. Marque-o como inativo.")
            return redirect(obj)
        return super().post(request, *args, **kwargs)
