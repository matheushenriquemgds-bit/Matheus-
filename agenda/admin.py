from django.contrib import admin

from .models import Compromisso


@admin.register(Compromisso)
class CompromissoAdmin(admin.ModelAdmin):
    list_display = ("data", "hora", "tipo", "titulo", "processo", "responsavel", "concluido")
    list_filter = ("tipo", "concluido", "responsavel")
    search_fields = ("titulo", "processo__numero")
    date_hierarchy = "data"
