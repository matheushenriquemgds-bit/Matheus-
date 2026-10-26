from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from core.forms import DataInput, FormBase
from core.utils import cnj_valido, so_digitos
from core.views import Criar, Editar, Excluir, Lista
from publicacoes.models import Publicacao
from publicacoes.servicos import registrar

from .models import Andamento, Processo


class ProcessoForm(FormBase):
    class Meta:
        model = Processo
        exclude = ["criado_em", "atualizado_em", "numero_digitos"]
        widgets = {"data_distribuicao": DataInput(), "observacoes": forms.Textarea()}

    def clean_numero(self):
        numero = self.cleaned_data["numero"].strip()
        digitos = so_digitos(numero)
        if len(digitos) == 20 and not cnj_valido(digitos):
            raise forms.ValidationError("Dígito verificador inválido para o número CNJ informado.")
        duplicado = Processo.objects.filter(numero_digitos=digitos).exclude(pk=self.instance.pk)
        if digitos and duplicado.exists():
            raise forms.ValidationError("Já existe um processo cadastrado com este número.")
        return numero


class AndamentoForm(FormBase):
    class Meta:
        model = Andamento
        fields = ["data", "descricao"]
        widgets = {"data": DataInput(), "descricao": forms.Textarea(attrs={"rows": 2})}


class ProcessoLista(Lista):
    model = Processo
    campos_busca = ("numero", "numero_digitos", "cliente__nome", "parte_contraria", "titulo", "tribunal", "orgao")
    filtros = ("situacao", "area", "responsavel")

    def get_queryset(self):
        return super().get_queryset().select_related("cliente", "responsavel")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(situacoes=Processo.SITUACOES, areas=Processo.AREAS,
                   usuarios=get_user_model().objects.filter(is_active=True))
        return ctx


class ProcessoDetalhe(DetailView):
    model = Processo

    def get_queryset(self):
        return super().get_queryset().select_related("cliente", "responsavel")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        p = self.object
        ctx.update(
            andamentos=p.andamentos.select_related("autor"),
            publicacoes=p.publicacoes.all()[:20],
            compromissos=p.compromissos.select_related("responsavel"),
            lancamentos=p.lancamentos.all(),
            andamento_form=AndamentoForm(),
        )
        return ctx


class VincularPublicacoesMixin:
    """Publicações já recebidas com o número do processo passam a apontar para ele."""

    def form_valid(self, form):
        resposta = super().form_valid(form)
        pendentes = Publicacao.objects.filter(numero_digitos=self.object.numero_digitos, processo__isnull=True)
        for pub in pendentes:
            registrar(pub)
        return resposta


class ProcessoCriar(VincularPublicacoesMixin, Criar):
    model = Processo
    form_class = ProcessoForm
    mensagem = "Processo cadastrado."

    def get_initial(self):
        inicial = super().get_initial()
        inicial["responsavel"] = self.request.user
        if self.request.GET.get("cliente"):
            inicial["cliente"] = self.request.GET["cliente"]
        if self.request.GET.get("numero"):
            inicial["numero"] = self.request.GET["numero"]
        return inicial


class ProcessoEditar(VincularPublicacoesMixin, Editar):
    model = Processo
    form_class = ProcessoForm
    mensagem = "Processo atualizado."


class ProcessoExcluir(Excluir):
    model = Processo
    success_url = reverse_lazy("processos:lista")


@require_POST
def andamento_criar(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    form = AndamentoForm(request.POST)
    if form.is_valid():
        andamento = form.save(commit=False)
        andamento.processo = processo
        andamento.autor = request.user
        andamento.save()
        messages.success(request, "Andamento registrado.")
    else:
        messages.error(request, "Preencha a data e a descrição do andamento.")
    return redirect(processo)


@require_POST
def andamento_excluir(request, pk):
    andamento = get_object_or_404(Andamento, pk=pk)
    andamento.delete()
    messages.success(request, "Andamento excluído.")
    return redirect(andamento.processo)
