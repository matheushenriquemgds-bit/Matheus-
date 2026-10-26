from django.contrib import admin

from .models import OABMonitorada, Publicacao


@admin.register(OABMonitorada)
class OABMonitoradaAdmin(admin.ModelAdmin):
    list_display = ("advogado", "numero", "uf", "ativa", "ultima_busca")


@admin.register(Publicacao)
class PublicacaoAdmin(admin.ModelAdmin):
    list_display = ("data_disponibilizacao", "numero_processo", "tribunal", "tipo", "lida", "processo")
    list_filter = ("lida", "origem", "tribunal")
    search_fields = ("numero_processo", "texto")
    date_hierarchy = "data_disponibilizacao"
