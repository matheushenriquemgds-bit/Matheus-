from django.contrib import admin

from .models import Lancamento


@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ("vencimento", "tipo", "categoria", "descricao", "valor", "cliente", "pago")
    list_filter = ("tipo", "categoria", "pago")
    search_fields = ("descricao", "cliente__nome")
    date_hierarchy = "vencimento"
