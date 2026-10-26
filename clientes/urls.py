from django.urls import path

from . import views

app_name = "clientes"
urlpatterns = [
    path("", views.ClienteLista.as_view(), name="lista"),
    path("novo/", views.ClienteCriar.as_view(), name="criar"),
    path("<int:pk>/", views.ClienteDetalhe.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.ClienteEditar.as_view(), name="editar"),
    path("<int:pk>/excluir/", views.ClienteExcluir.as_view(), name="excluir"),
]
