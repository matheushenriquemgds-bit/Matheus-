from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from agenda.models import Compromisso
from core.forms import DataInput, EstiloBootstrap, FormBase
from core.models import Feriado
from core.utils import eh_dia_util, proximo_dia_util, vencimento_por_disponibilizacao
from core.views import Criar, Editar, Excluir, Lista, voltar_para
from processos.models import Processo

from . import servicos
from .models import OABMonitorada, Publicacao


class PublicacaoForm(FormBase):
    class Meta:
        model = Publicacao
        fields = ["data_disponibilizacao", "numero_processo", "tribunal", "orgao", "tipo", "texto", "processo"]
        widgets = {"data_disponibilizacao": DataInput(), "texto": forms.Textarea(attrs={"rows": 8})}


class OABForm(FormBase):
    class Meta:
        model = OABMonitorada
        fields = ["advogado", "numero", "uf", "usuario", "ativa"]


class BuscaForm(EstiloBootstrap, forms.Form):
    inicio = forms.DateField(label="De", widget=DataInput())
    fim = forms.DateField(label="Até", widget=DataInput())

    def clean(self):
        dados = super().clean()
        if dados.get("inicio") and dados.get("fim") and dados["inicio"] > dados["fim"]:
            raise forms.ValidationError("A data inicial deve ser anterior à final.")
        return dados


class PrazoForm(EstiloBootstrap, forms.Form):
    titulo = forms.CharField(label="Título", max_length=200)
    dias = forms.IntegerField(label="Prazo (dias)", min_value=1, max_value=365, initial=15)
    contagem = forms.ChoiceField(
        label="Contagem", choices=[("uteis", "Dias úteis (CPC)"), ("corridos", "Dias corridos")], initial="uteis"
    )
    responsavel = forms.ModelChoiceField(
        label="Responsável", queryset=get_user_model().objects.filter(is_active=True), required=False
    )

    def vencimento(self, disponibilizacao):
        dias, feriados = self.cleaned_data["dias"], Feriado.datas()
        if self.cleaned_data["contagem"] == "uteis":
            return vencimento_por_disponibilizacao(disponibilizacao, dias, feriados_extras=feriados)
        # Corridos: conta da publicação (dia seguinte à disponibilização) e, se o
        # término cair em dia não útil, prorroga para o próximo dia útil.
        fim = disponibilizacao + timedelta(days=dias + 1)
        if not eh_dia_util(fim, feriados_extras=feriados):
            fim = proximo_dia_util(fim, feriados_extras=feriados)
        return fim


class PublicacaoLista(Lista):
    model = Publicacao
    campos_busca = ("texto", "numero_processo", "orgao", "destinatarios", "processo__cliente__nome")
    filtros = ("tribunal", "oab")

    def get_queryset(self):
        qs = super().get_queryset().select_related("processo__cliente", "oab")
        status = self.request.GET.get("status", "nao_lidas")
        if status == "nao_lidas":
            qs = qs.filter(lida=False)
        elif status == "lidas":
            qs = qs.filter(lida=True)
        if self.request.GET.get("vinculo") == "sem":
            qs = qs.filter(processo__isnull=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        ctx.update(
            status=self.request.GET.get("status", "nao_lidas"),
            oabs=OABMonitorada.objects.all(),
            tribunais=Publicacao.objects.exclude(tribunal="").values_list("tribunal", flat=True)
            .distinct().order_by("tribunal"),
            busca_form=BuscaForm(initial={"inicio": hoje - timedelta(days=7), "fim": hoje}),
        )
        return ctx


class PublicacaoDetalhe(DetailView):
    model = Publicacao

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pub = self.object
        feriados = Feriado.datas()
        processo = pub.processo
        ctx.update(
            prazo_form=PrazoForm(initial={
                "titulo": f"Prazo — {pub.tipo or 'publicação'}" + (f" ({processo.cliente})" if processo else ""),
                "responsavel": (processo.responsavel if processo else None) or self.request.user,
            }),
            simulacao=[
                (d, vencimento_por_disponibilizacao(pub.data_disponibilizacao, d, feriados_extras=feriados))
                for d in (5, 8, 15, 30)
            ],
            processos=Processo.objects.select_related("cliente").order_by("numero") if not processo else None,
        )
        return ctx


class PublicacaoCriar(Criar):
    model = Publicacao
    form_class = PublicacaoForm
    mensagem = "Publicação cadastrada."

    def form_valid(self, form):
        form.instance.origem = Publicacao.MANUAL
        self.object = servicos.registrar(form.save(commit=False))
        messages.success(self.request, self.mensagem)
        return redirect(self.object)


class PublicacaoEditar(Editar):
    model = Publicacao
    form_class = PublicacaoForm
    mensagem = "Publicação atualizada."


class PublicacaoExcluir(Excluir):
    model = Publicacao
    success_url = reverse_lazy("publicacoes:lista")


def _marcar(pub, usuario, lida):
    pub.lida = lida
    pub.lida_por = usuario if lida else None
    pub.lida_em = timezone.now() if lida else None
    pub.save(update_fields=["lida", "lida_por", "lida_em"])


@require_POST
def marcar_lida(request, pk):
    pub = get_object_or_404(Publicacao, pk=pk)
    _marcar(pub, request.user, request.POST.get("lida", "1") == "1")
    if request.POST.get("proxima"):
        proxima = Publicacao.objects.filter(lida=False).exclude(pk=pub.pk).first()
        if proxima:
            return redirect(proxima)
        messages.success(request, "Todas as publicações foram lidas.")
        return redirect("publicacoes:lista")
    return redirect(pub)


@require_POST
def marcar_varias(request):
    ids = request.POST.getlist("ids")
    pubs = Publicacao.objects.filter(pk__in=ids, lida=False)
    total = pubs.update(lida=True, lida_por=request.user, lida_em=timezone.now())
    messages.success(request, f"{total} publicação(ões) marcada(s) como lida(s).")
    return redirect(voltar_para(request, "publicacoes:lista"))


@require_POST
def vincular(request, pk):
    pub = get_object_or_404(Publicacao, pk=pk)
    processo = get_object_or_404(Processo, pk=request.POST.get("processo"))
    pub.processo = processo
    servicos.registrar(pub)
    messages.success(request, f"Publicação vinculada ao processo {processo}.")
    return redirect(pub)


@require_POST
def criar_prazo(request, pk):
    pub = get_object_or_404(Publicacao, pk=pk)
    form = PrazoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Verifique os dados do prazo.")
        return redirect(pub)
    vencimento = form.vencimento(pub.data_disponibilizacao)
    prazo = Compromisso.objects.create(
        tipo=Compromisso.PRAZO,
        titulo=form.cleaned_data["titulo"],
        descricao=f"Gerado a partir da publicação de {pub.data_disponibilizacao:%d/%m/%Y} "
        f"({form.cleaned_data['dias']} dias {'úteis' if form.cleaned_data['contagem'] == 'uteis' else 'corridos'}).",
        data=vencimento,
        processo=pub.processo,
        publicacao=pub,
        responsavel=form.cleaned_data["responsavel"],
    )
    _marcar(pub, request.user, True)
    messages.success(request, f"Prazo criado com vencimento em {prazo.data:%d/%m/%Y}. Confira a data.")
    return redirect(pub)


@require_POST
def buscar_agora(request):
    form = BuscaForm(request.POST)
    if not OABMonitorada.objects.filter(ativa=True).exists():
        messages.warning(request, "Cadastre ao menos uma OAB para buscar publicações.")
        return redirect("publicacoes:oabs")
    if not form.is_valid():
        messages.error(request, "Período inválido.")
        return redirect("publicacoes:lista")
    novas, erros = servicos.buscar_todas(form.cleaned_data["inicio"], form.cleaned_data["fim"])
    for erro in erros:
        messages.error(request, erro)
    messages.success(request, f"Busca concluída: {novas} nova(s) publicação(ões).")
    return redirect("publicacoes:lista")


class OABLista(Lista):
    model = OABMonitorada
    template_name = "publicacoes/oab_list.html"


class OABCriar(Criar):
    model = OABMonitorada
    form_class = OABForm
    success_url = reverse_lazy("publicacoes:oabs")
    mensagem = "OAB cadastrada. As publicações serão buscadas na próxima atualização."


class OABEditar(Editar):
    model = OABMonitorada
    form_class = OABForm
    success_url = reverse_lazy("publicacoes:oabs")


class OABExcluir(Excluir):
    model = OABMonitorada
    success_url = reverse_lazy("publicacoes:oabs")
