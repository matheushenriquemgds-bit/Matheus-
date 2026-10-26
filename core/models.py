from django.db import models


class Feriado(models.Model):
    """Feriados locais/forenses que o escritório quer descontar na contagem de prazos."""

    data = models.DateField(unique=True)
    descricao = models.CharField("descrição", max_length=120)

    class Meta:
        ordering = ["data"]

    def __str__(self):
        return f"{self.data:%d/%m/%Y} — {self.descricao}"

    @classmethod
    def datas(cls):
        return frozenset(cls.objects.values_list("data", flat=True))


class Registro(models.Model):
    """Base com datas de criação/alteração."""

    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True
