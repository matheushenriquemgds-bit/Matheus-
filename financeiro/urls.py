from django.urls import path

from . import views

app_name = "financeiro"
urlpatterns = [
    path("", views.LancamentoLista.as_view(), name="lista"),
    path("novo/", views.LancamentoCriar.as_view(), name="criar"),
    path("<int:pk>/editar/", views.LancamentoEditar.as_view(), name="editar"),
    path("<int:pk>/excluir/", views.LancamentoExcluir.as_view(), name="excluir"),
    path("<int:pk>/pago/", views.alternar_pago, name="alternar_pago"),
]
