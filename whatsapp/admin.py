from django.contrib import admin

from .models import Configuracao, Conversa, Mensagem, Solicitacao


@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not Configuracao.objects.exists()


class MensagemInline(admin.TabularInline):
    model = Mensagem
    extra = 0
    fields = ("criada_em", "autor", "tipo", "texto", "arquivo", "erro")
    readonly_fields = fields


@admin.register(Conversa)
class ConversaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "telefone", "cliente", "bot_pausado", "ultima_mensagem_em")
    list_filter = ("bot_pausado",)
    search_fields = ("nome", "telefone", "cliente__nome")
    autocomplete_fields = ("cliente",)
    inlines = [MensagemInline]


@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    list_display = ("resumo", "tipo", "conversa", "resolvida", "criado_em")
    list_filter = ("tipo", "resolvida")
    search_fields = ("resumo", "detalhes", "conversa__nome", "conversa__telefone")
