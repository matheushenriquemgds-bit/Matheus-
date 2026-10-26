from django.conf import settings
from django.db import models
from django.urls import reverse

from clientes.models import UFS
from core.utils import formatar_cnj, so_digitos


class OABMonitorada(models.Model):
    """Inscrição na OAB cujas comunicações são buscadas automaticamente."""

    numero = models.CharField("número OAB", max_length=10, help_text="Apenas números, ex.: 123456")
    uf = models.CharField("UF", max_length=2, choices=UFS)
    advogado = models.CharField("nome do advogado", max_length=150)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuário", on_delete=models.SET_NULL, null=True, blank=True
    )
    ativa = models.BooleanField(default=True)
    ultima_busca = models.DateField("buscado até", null=True, blank=True)

    class Meta:
        verbose_name = "OAB monitorada"
        verbose_name_plural = "OABs monitoradas"
        unique_together = [("numero", "uf")]
        ordering = ["advogado"]

    def __str__(self):
        return f"{self.advogado} — OAB/{self.uf} {self.numero}"


class Publicacao(models.Model):
    MANUAL, DJEN = "manual", "djen"

    ORIGENS = [(MANUAL, "Manual"), (DJEN, "DJEN / Comunica PJe")]

    origem = models.CharField(max_length=10, choices=ORIGENS, default=MANUAL)
    id_externo = models.CharField("identificador externo", max_length=80, unique=True, null=True, blank=True)
    oab = models.ForeignKey(
        OABMonitorada, verbose_name="OAB", on_delete=models.SET_NULL, null=True, blank=True, related_name="publicacoes"
    )
    data_disponibilizacao = models.DateField("disponibilizada em")
    tribunal = models.CharField(max_length=20, blank=True)
    orgao = models.CharField("órgão", max_length=250, blank=True)
    tipo = models.CharField("tipo de comunicação", max_length=80, blank=True)
    numero_processo = models.CharField("número do processo", max_length=30, blank=True)
    numero_digitos = models.CharField(max_length=25, blank=True, db_index=True, editable=False)
    texto = models.TextField()
    link = models.URLField(max_length=500, blank=True)
    destinatarios = models.TextField("partes", blank=True)
    advogados = models.TextField(blank=True)

    processo = models.ForeignKey(
        "processos.Processo", on_delete=models.SET_NULL, null=True, blank=True, related_name="publicacoes"
    )
    lida = models.BooleanField(default=False)
    lida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    lida_em = models.DateTimeField(null=True, blank=True)
    recebida_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "publicação"
        verbose_name_plural = "publicações"
        ordering = ["-data_disponibilizacao", "-recebida_em"]

    def __str__(self):
        return f"{self.data_disponibilizacao:%d/%m/%Y} — {self.numero_processo or 'sem número'}"

    def get_absolute_url(self):
        return reverse("publicacoes:detalhe", args=[self.pk])

    def _normalizar_numero(self):
        self.numero_processo = formatar_cnj(self.numero_processo.strip())
        self.numero_digitos = so_digitos(self.numero_processo)

    def save(self, *args, **kwargs):
        self._normalizar_numero()
        super().save(*args, **kwargs)

    def vincular_processo(self):
        """Associa ao processo cadastrado com o mesmo número CNJ, se houver."""
        from processos.models import Processo

        self._normalizar_numero()
        if self.processo_id or not self.numero_digitos:
            return self.processo
        self.processo = Processo.objects.filter(numero_digitos=self.numero_digitos).first()
        return self.processo
