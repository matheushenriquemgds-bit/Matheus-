from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import Registro


class Compromisso(Registro):
    PRAZO, AUDIENCIA, TAREFA, REUNIAO = "prazo", "audiencia", "tarefa", "reuniao"
    TIPOS = [(PRAZO, "Prazo"), (AUDIENCIA, "Audiência"), (TAREFA, "Tarefa"), (REUNIAO, "Reunião")]

    tipo = models.CharField(max_length=10, choices=TIPOS, default=PRAZO)
    titulo = models.CharField("título", max_length=200)
    descricao = models.TextField("descrição", blank=True)
    data = models.DateField(help_text="Para prazos, a data fatal.")
    hora = models.TimeField(null=True, blank=True)
    local = models.CharField(max_length=200, blank=True, help_text="Sala, endereço ou link da audiência")

    processo = models.ForeignKey(
        "processos.Processo", on_delete=models.CASCADE, null=True, blank=True, related_name="compromissos"
    )
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.CASCADE, null=True, blank=True, related_name="compromissos"
    )
    publicacao = models.ForeignKey(
        "publicacoes.Publicacao", verbose_name="publicação de origem", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="compromissos",
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="responsável", on_delete=models.SET_NULL, null=True, blank=True
    )
    concluido = models.BooleanField("concluído", default=False)
    concluido_em = models.DateTimeField("concluído em", null=True, blank=True)

    class Meta:
        ordering = ["concluido", "data", "hora"]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.titulo}"

    def get_absolute_url(self):
        return reverse("agenda:editar", args=[self.pk])

    @property
    def situacao(self):
        """'concluido', 'atrasado', 'hoje' ou 'futuro' — usado para colorir a interface."""
        if self.concluido:
            return "concluido"
        hoje = timezone.localdate()
        if self.data < hoje:
            return "atrasado"
        return "hoje" if self.data == hoje else "futuro"

    def save(self, *args, **kwargs):
        if self.processo_id and not self.cliente_id:
            self.cliente_id = self.processo.cliente_id
        self.concluido_em = (self.concluido_em or timezone.now()) if self.concluido else None
        super().save(*args, **kwargs)
