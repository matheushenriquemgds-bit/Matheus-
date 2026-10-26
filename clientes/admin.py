from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "cpf_cnpj", "celular", "cidade", "ativo")
    list_filter = ("tipo", "ativo", "uf")
    search_fields = ("nome", "cpf_cnpj", "email")
