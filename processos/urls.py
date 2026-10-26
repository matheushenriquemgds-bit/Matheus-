from django.urls import path

from . import views

app_name = "processos"
urlpatterns = [
    path("", views.ProcessoLista.as_view(), name="lista"),
    path("novo/", views.ProcessoCriar.as_view(), name="criar"),
    path("<int:pk>/", views.ProcessoDetalhe.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.ProcessoEditar.as_view(), name="editar"),
    path("<int:pk>/excluir/", views.ProcessoExcluir.as_view(), name="excluir"),
    path("<int:pk>/andamentos/novo/", views.andamento_criar, name="andamento_criar"),
    path("andamentos/<int:pk>/excluir/", views.andamento_excluir, name="andamento_excluir"),
]
