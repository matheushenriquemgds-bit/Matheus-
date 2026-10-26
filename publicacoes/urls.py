from django.urls import path

from . import views

app_name = "publicacoes"
urlpatterns = [
    path("", views.PublicacaoLista.as_view(), name="lista"),
    path("nova/", views.PublicacaoCriar.as_view(), name="criar"),
    path("buscar/", views.buscar_agora, name="buscar"),
    path("marcar-lidas/", views.marcar_varias, name="marcar_varias"),
    path("<int:pk>/", views.PublicacaoDetalhe.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.PublicacaoEditar.as_view(), name="editar"),
    path("<int:pk>/excluir/", views.PublicacaoExcluir.as_view(), name="excluir"),
    path("<int:pk>/lida/", views.marcar_lida, name="marcar_lida"),
    path("<int:pk>/vincular/", views.vincular, name="vincular"),
    path("<int:pk>/prazo/", views.criar_prazo, name="criar_prazo"),
    path("oabs/", views.OABLista.as_view(), name="oabs"),
    path("oabs/nova/", views.OABCriar.as_view(), name="oab_criar"),
    path("oabs/<int:pk>/editar/", views.OABEditar.as_view(), name="oab_editar"),
    path("oabs/<int:pk>/excluir/", views.OABExcluir.as_view(), name="oab_excluir"),
]
