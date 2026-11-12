import json
import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from clientes.models import Cliente
from core.forms import EstiloBootstrap, FormBase
from core.views import Editar, Lista, voltar_para

from . import api, servico
from .models import Configuracao, Conversa, Mensagem, Solicitacao

log = logging.getLogger(__name__)


# --- Webhook chamado pela Meta -------------------------------------------------------------------

@csrf_exempt
@login_not_required
def webhook(request):
    if request.method == "GET":
        # Verificação feita pela Meta ao cadastrar o webhook.
        token = settings.WHATSAPP_VERIFY_TOKEN
        if (request.GET.get("hub.mode") == "subscribe" and token
                and request.GET.get("hub.verify_token") == token):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponseForbidden("Token de verificação inválido.")
    if request.method != "POST":
        return HttpResponse(status=405)

    if not api.assinatura_valida(request.body, request.headers.get("X-Hub-Signature-256")):
        log.warning("Webhook do WhatsApp com assinatura inválida (confira WHATSAPP_APP_SECRET).")
        return HttpResponseForbidden("Assinatura inválida.")
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except ValueError:
        return HttpResponseBadRequest("JSON inválido.")
    servico.agendar_respostas(servico.processar_webhook(payload))
    return HttpResponse("ok")


# --- Telas da equipe -----------------------------------------------------------------------------

class RespostaForm(EstiloBootstrap, forms.Form):
    texto = forms.CharField(label="Mensagem", widget=forms.Textarea(attrs={"rows": 3}), max_length=4000)


class VincularForm(EstiloBootstrap, forms.Form):
    cliente = forms.ModelChoiceField(label="Cliente", queryset=Cliente.objects.filter(ativo=True), required=False)


class ConfiguracaoForm(FormBase):
    class Meta:
        model = Configuracao
        fields = ["bot_ativo", "nome_escritorio", "informacoes", "documentos"]
        widgets = {"informacoes": forms.Textarea(attrs={"rows": 10}), "documentos": forms.Textarea(attrs={"rows": 8})}


class ConversaLista(Lista):
    model = Conversa
    campos_busca = ("nome", "telefone", "cliente__nome")

    def get_queryset(self):
        qs = super().get_queryset().select_related("cliente")
        filtro = self.request.GET.get("filtro")
        if filtro == "nao_lidas":
            qs = qs.filter(nao_lida=True)
        elif filtro == "equipe":
            qs = qs.filter(bot_pausado=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            filtro=self.request.GET.get("filtro", ""),
            config=Configuracao.atual(),
            whatsapp_configurado=api.configurado(),
            pendentes=Solicitacao.objects.filter(resolvida=False).count(),
        )
        return ctx


class ConversaDetalhe(DetailView):
    model = Conversa

    def get_object(self, queryset=None):
        conversa = super().get_object(queryset)
        if conversa.nao_lida:
            conversa.nao_lida = False
            conversa.save(update_fields=["nao_lida"])
        return conversa

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        ctx.update(
            mensagens=c.mensagens.select_related("usuario"),
            solicitacoes=c.solicitacoes.filter(resolvida=False),
            resposta_form=RespostaForm(),
            vincular_form=VincularForm(initial={"cliente": c.cliente}),
            config=Configuracao.atual(),
        )
        return ctx


@require_POST
def responder(request, pk):
    conversa = get_object_or_404(Conversa, pk=pk)
    form = RespostaForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Escreva a mensagem.")
        return redirect(conversa)
    if not conversa.janela_aberta:
        messages.warning(request, "Já se passaram 24 horas desde a última mensagem do contato. O WhatsApp só "
                                  "permite responder depois que ele escrever de novo.")
    if not conversa.bot_pausado:
        conversa.bot_pausado = True
        conversa.save(update_fields=["bot_pausado", "atualizado_em"])
        messages.info(request, "O robô foi pausado nesta conversa enquanto a equipe atende.")
    mensagem = servico.enviar(conversa, form.cleaned_data["texto"], autor=Mensagem.EQUIPE, usuario=request.user)
    if mensagem.erro:
        messages.error(request, f"A mensagem não foi enviada: {mensagem.erro}")
    return redirect(conversa)


@require_POST
def alternar_robo(request, pk):
    conversa = get_object_or_404(Conversa, pk=pk)
    conversa.bot_pausado = not conversa.bot_pausado
    conversa.save(update_fields=["bot_pausado", "atualizado_em"])
    if conversa.bot_pausado:
        messages.success(request, "Robô pausado: a equipe atende esta conversa.")
    else:
        conversa.solicitacoes.filter(tipo=Solicitacao.ATENDENTE, resolvida=False).update(
            resolvida=True, resolvida_em=timezone.now(), resolvida_por=request.user
        )
        messages.success(request, "Conversa devolvida ao robô. Ele responde a partir da próxima mensagem do contato.")
    return redirect(conversa)


@require_POST
def vincular(request, pk):
    conversa = get_object_or_404(Conversa, pk=pk)
    form = VincularForm(request.POST)
    if form.is_valid():
        conversa.cliente = form.cleaned_data["cliente"]
        conversa.save(update_fields=["cliente", "atualizado_em"])
        messages.success(request, "Cliente vinculado." if conversa.cliente else "Vínculo removido.")
    return redirect(conversa)


def arquivo(request, pk):
    """Entrega os arquivos recebidos só para usuários logados (eles não ficam públicos)."""
    mensagem = get_object_or_404(Mensagem, pk=pk)
    if not mensagem.arquivo:
        raise Http404
    try:
        return FileResponse(mensagem.arquivo.open("rb"), as_attachment=request.GET.get("baixar") == "1",
                            filename=mensagem.descricao_arquivo)
    except FileNotFoundError as e:
        raise Http404 from e


class SolicitacaoLista(Lista):
    model = Solicitacao
    template_name = "whatsapp/solicitacao_list.html"
    filtros = ("tipo",)

    def get_queryset(self):
        qs = super().get_queryset().select_related("conversa__cliente", "resolvida_por")
        status = self.request.GET.get("status", "pendentes")
        if status == "pendentes":
            qs = qs.filter(resolvida=False)
        elif status == "resolvidas":
            qs = qs.filter(resolvida=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(status=self.request.GET.get("status", "pendentes"), tipos=Solicitacao.TIPOS)
        return ctx


@require_POST
def resolver(request, pk):
    s = get_object_or_404(Solicitacao, pk=pk)
    s.resolvida = not s.resolvida
    s.resolvida_em = timezone.now() if s.resolvida else None
    s.resolvida_por = request.user if s.resolvida else None
    s.save()
    messages.success(request, "Solicitação marcada como resolvida." if s.resolvida else "Solicitação reaberta.")
    return redirect(voltar_para(request, s.conversa.get_absolute_url()))


class ConfiguracaoEditar(Editar):
    model = Configuracao
    form_class = ConfiguracaoForm
    template_name = "whatsapp/configuracao.html"
    mensagem = "Configuração do robô salva."
    success_url = reverse_lazy("whatsapp:configuracao")

    def get_object(self, queryset=None):
        return Configuracao.atual()
