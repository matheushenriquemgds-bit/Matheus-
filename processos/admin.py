from django.contrib import admin

from .models import Andamento, Processo


class AndamentoInline(admin.TabularInline):
    model = Andamento
    extra = 0
    fields = ("data", "descricao", "origem")


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "tribunal", "area", "situacao", "responsavel")
    list_filter = ("situacao", "area", "tribunal")
    search_fields = ("numero", "numero_digitos", "cliente__nome", "parte_contraria")
    inlines = [AndamentoInline]
