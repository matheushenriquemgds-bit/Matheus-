from django.urls import path

from . import views

app_name = "agenda"
urlpatterns = [
    path("", views.CompromissoLista.as_view(), name="lista"),
    path("calendario/", views.Calendario.as_view(), name="calendario"),
    path("novo/", views.CompromissoCriar.as_view(), name="criar"),
    path("<int:pk>/editar/", views.CompromissoEditar.as_view(), name="editar"),
    path("<int:pk>/excluir/", views.CompromissoExcluir.as_view(), name="excluir"),
    path("<int:pk>/concluir/", views.concluir, name="concluir"),
]
