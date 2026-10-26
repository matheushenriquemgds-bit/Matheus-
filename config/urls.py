from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("entrar/", auth_views.LoginView.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("core.urls")),
    path("clientes/", include("clientes.urls")),
    path("processos/", include("processos.urls")),
    path("publicacoes/", include("publicacoes.urls")),
    path("agenda/", include("agenda.urls")),
    path("financeiro/", include("financeiro.urls")),
]

admin.site.site_header = "Escritório — Administração"
admin.site.site_title = "Escritório"
