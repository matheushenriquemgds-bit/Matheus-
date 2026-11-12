from django.urls import path

from . import views

app_name = "whatsapp"
urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
    path("", views.ConversaLista.as_view(), name="lista"),
    path("solicitacoes/", views.SolicitacaoLista.as_view(), name="solicitacoes"),
    path("solicitacoes/<int:pk>/resolver/", views.resolver, name="resolver"),
    path("configuracao/", views.ConfiguracaoEditar.as_view(), name="configuracao"),
    path("arquivo/<int:pk>/", views.arquivo, name="arquivo"),
    path("<int:pk>/", views.ConversaDetalhe.as_view(), name="conversa"),
    path("<int:pk>/responder/", views.responder, name="responder"),
    path("<int:pk>/robo/", views.alternar_robo, name="alternar_robo"),
    path("<int:pk>/vincular/", views.vincular, name="vincular"),
]
