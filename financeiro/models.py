from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import Registro


class Lancamento(Registro):
    RECEITA, DESPESA = "receita", "despesa"
    TIPOS = [(RECEITA, "Receita"), (DESPESA, "Despesa")]
    CATEGORIAS = [
        ("honorarios_contratuais", "Honorários contratuais"),
        ("honorarios_exito", "Honorários de êxito"),
        ("honorarios_sucumbencia", "Honorários de sucumbência"),
        ("consulta", "Consulta / parecer"),
        ("reembolso", "Reembolso de despesas"),
        ("custas", "Custas processuais"),
        ("diligencia", "Diligências / deslocamento"),
        ("pericia", "Perícia"),
        ("escritorio", "Despesas do escritório"),
        ("impostos", "Impostos"),
        ("outros", "Outros"),
    ]

    tipo = models.CharField(max_length=10, choices=TIPOS, default=RECEITA)
    categoria = models.CharField(max_length=30, choices=CATEGORIAS, default="honorarios_contratuais")
    descricao = models.CharField("descrição", max_length=200)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    vencimento = models.DateField()
    pago = models.BooleanField("pago / recebido", default=False)
    data_pagamento = models.DateField("data do pagamento", null=True, blank=True)
    forma_pagamento = models.CharField("forma de pagamento", max_length=40, blank=True, help_text="PIX, boleto…")
    parcela = models.CharField(max_length=10, blank=True, help_text="Ex.: 2/10")

    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos"
    )
    processo = models.ForeignKey(
        "processos.Processo", on_delete=models.SET_NULL, null=True, blank=True, related_name="lancamentos"
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "lançamento"
        ordering = ["pago", "vencimento"]

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return reverse("financeiro:editar", args=[self.pk])

    @property
    def vencido(self):
        return not self.pago and self.vencimento < timezone.localdate()

    def save(self, *args, **kwargs):
        if self.processo_id and not self.cliente_id:
            self.cliente_id = self.processo.cliente_id
        if self.pago and not self.data_pagamento:
            self.data_pagamento = timezone.localdate()
        if not self.pago:
            self.data_pagamento = None
        super().save(*args, **kwargs)
