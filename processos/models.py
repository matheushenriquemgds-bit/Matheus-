from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import Registro
from core.utils import formatar_cnj, so_digitos


class Processo(Registro):
    ATIVO, SUSPENSO, ARQUIVADO, ENCERRADO = "ativo", "suspenso", "arquivado", "encerrado"
    SITUACOES = [(ATIVO, "Ativo"), (SUSPENSO, "Suspenso"), (ARQUIVADO, "Arquivado"), (ENCERRADO, "Encerrado")]
    AREAS = [
        ("civel", "Cível"),
        ("trabalhista", "Trabalhista"),
        ("previdenciario", "Previdenciário"),
        ("tributario", "Tributário"),
        ("familia", "Família e Sucessões"),
        ("consumidor", "Consumidor"),
        ("criminal", "Criminal"),
        ("administrativo", "Administrativo"),
        ("empresarial", "Empresarial"),
        ("outra", "Outra"),
    ]
    POLOS = [("ativo", "Polo ativo (autor)"), ("passivo", "Polo passivo (réu)"), ("terceiro", "Terceiro interessado")]

    numero = models.CharField("número do processo", max_length=30, help_text="Formato CNJ: 0000000-00.0000.0.00.0000")
    numero_digitos = models.CharField(max_length=25, db_index=True, editable=False)
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="processos")
    polo_cliente = models.CharField("polo do cliente", max_length=10, choices=POLOS, default="ativo")
    parte_contraria = models.CharField("parte contrária", max_length=200, blank=True)

    titulo = models.CharField("título / ação", max_length=200, blank=True, help_text="Ex.: Ação de cobrança")
    area = models.CharField("área", max_length=20, choices=AREAS, default="civel")
    classe = models.CharField(max_length=150, blank=True)
    assunto = models.CharField(max_length=200, blank=True)
    tribunal = models.CharField(max_length=20, blank=True, help_text="Sigla, ex.: TJSP, TRT2, TRF3")
    orgao = models.CharField("vara / órgão julgador", max_length=200, blank=True)
    comarca = models.CharField("comarca / foro", max_length=120, blank=True)
    instancia = models.CharField("instância", max_length=20, blank=True, help_text="Ex.: 1º grau")

    valor_causa = models.DecimalField("valor da causa", max_digits=14, decimal_places=2, null=True, blank=True)
    data_distribuicao = models.DateField("data de distribuição", null=True, blank=True)
    situacao = models.CharField("situação", max_length=10, choices=SITUACOES, default=ATIVO)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="advogado responsável", on_delete=models.SET_NULL, null=True, blank=True
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.numero

    def save(self, *args, **kwargs):
        self.numero = formatar_cnj(self.numero.strip())
        self.numero_digitos = so_digitos(self.numero)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("processos:detalhe", args=[self.pk])


class Andamento(models.Model):
    MANUAL, PUBLICACAO = "manual", "publicacao"

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="andamentos")
    data = models.DateField(default=timezone.localdate)
    descricao = models.TextField("descrição")
    origem = models.CharField(max_length=12, choices=[(MANUAL, "Manual"), (PUBLICACAO, "Publicação")], default=MANUAL)
    publicacao = models.OneToOneField(
        "publicacoes.Publicacao", on_delete=models.SET_NULL, null=True, blank=True, related_name="andamento"
    )
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return f"{self.data:%d/%m/%Y} — {self.descricao[:60]}"
