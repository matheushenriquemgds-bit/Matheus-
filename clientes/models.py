from django.conf import settings
from django.db import models
from django.urls import reverse

from core.models import Registro
from core.utils import so_digitos

UFS = [(uf, uf) for uf in (
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)]


class Cliente(Registro):
    PF, PJ = "PF", "PJ"
    TIPOS = [(PF, "Pessoa física"), (PJ, "Pessoa jurídica")]
    ESTADOS_CIVIS = [
        ("solteiro", "Solteiro(a)"),
        ("casado", "Casado(a)"),
        ("uniao_estavel", "União estável"),
        ("divorciado", "Divorciado(a)"),
        ("viuvo", "Viúvo(a)"),
    ]

    tipo = models.CharField(max_length=2, choices=TIPOS, default=PF)
    nome = models.CharField("nome / razão social", max_length=200)
    cpf_cnpj = models.CharField("CPF / CNPJ", max_length=18, blank=True)
    rg = models.CharField("RG / inscrição estadual", max_length=30, blank=True)
    data_nascimento = models.DateField("data de nascimento", null=True, blank=True)
    estado_civil = models.CharField("estado civil", max_length=20, choices=ESTADOS_CIVIS, blank=True)
    profissao = models.CharField("profissão", max_length=100, blank=True)

    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    celular = models.CharField("celular / WhatsApp", max_length=20, blank=True)

    cep = models.CharField("CEP", max_length=9, blank=True)
    logradouro = models.CharField(max_length=200, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UFS, blank=True)

    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="responsável", on_delete=models.SET_NULL, null=True, blank=True
    )
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return reverse("clientes:detalhe", args=[self.pk])

    @property
    def documento_formatado(self):
        d = so_digitos(self.cpf_cnpj)
        if len(d) == 11:
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        if len(d) == 14:
            return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
        return self.cpf_cnpj

    @property
    def endereco(self):
        partes = [
            ", ".join(p for p in (self.logradouro, self.numero, self.complemento) if p),
            self.bairro,
            " / ".join(p for p in (self.cidade, self.uf) if p),
            self.cep,
        ]
        return " — ".join(p for p in partes if p)
