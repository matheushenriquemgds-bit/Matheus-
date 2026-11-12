from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import Registro
from core.utils import so_digitos


def chave_telefone(numero):
    """DDD + últimos 8 dígitos, para comparar números com ou sem +55 e com ou sem o nono dígito."""
    d = so_digitos(numero)
    if len(d) >= 12 and d.startswith("55"):
        d = d[2:]
    if len(d) < 10:
        return ""
    return d[:2] + d[-8:]


class Configuracao(models.Model):
    """Configuração única do robô de atendimento (sempre o registro de id 1)."""

    bot_ativo = models.BooleanField(
        "robô ligado", default=True,
        help_text="Desligado, as mensagens continuam chegando ao sistema, mas ninguém responde automaticamente.",
    )
    nome_escritorio = models.CharField("nome do escritório", max_length=150, default="nosso escritório")
    informacoes = models.TextField(
        "informações do escritório", blank=True,
        help_text="Tudo o que o robô pode contar aos clientes: endereço, horário, áreas de atuação, como funciona "
                  "a primeira consulta, formas de pagamento etc. O robô não informa nada que não esteja aqui.",
    )
    documentos = models.TextField(
        "documentos por tipo de caso", blank=True,
        help_text="Quais documentos pedir em cada situação. Ex.: \"Aposentadoria: RG, CPF, carteira de trabalho, "
                  "CNIS\". Sem essa lista, o robô pede apenas documento com foto e comprovante de residência.",
    )

    class Meta:
        verbose_name = "configuração do robô"
        verbose_name_plural = "configuração do robô"

    def __str__(self):
        return "Configuração do robô"

    @classmethod
    def atual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Conversa(Registro):
    telefone = models.CharField(max_length=20, unique=True, help_text="Número no formato do WhatsApp (só dígitos)")
    nome = models.CharField("nome no WhatsApp", max_length=150, blank=True)
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.SET_NULL, null=True, blank=True, related_name="conversas"
    )
    bot_pausado = models.BooleanField(
        "atendimento humano", default=False,
        help_text="Enquanto marcado, o robô não responde esta conversa.",
    )
    nao_lida = models.BooleanField("não lida", default=False)
    ultima_mensagem_em = models.DateTimeField("última mensagem", null=True, blank=True)
    ultima_entrada_em = models.DateTimeField("última mensagem do contato", null=True, blank=True)

    class Meta:
        ordering = ["-ultima_mensagem_em"]

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return reverse("whatsapp:conversa", args=[self.pk])

    @property
    def titulo(self):
        return str(self.cliente) if self.cliente else (self.nome or self.telefone_formatado)

    @property
    def telefone_formatado(self):
        d = self.telefone
        if len(d) == 13 and d.startswith("55"):
            return f"+55 ({d[2:4]}) {d[4:9]}-{d[9:]}"
        if len(d) == 12 and d.startswith("55"):
            return f"+55 ({d[2:4]}) {d[4:8]}-{d[8:]}"
        return f"+{d}"

    @property
    def janela_aberta(self):
        """O WhatsApp só permite mensagens livres até 24 h depois da última mensagem do contato."""
        return bool(self.ultima_entrada_em) and timezone.now() - self.ultima_entrada_em < timedelta(hours=24)

    def localizar_cliente(self):
        """Vincula ao cliente cujo celular ou telefone é o deste contato, se houver exatamente um."""
        from clientes.models import Cliente

        chave = chave_telefone(self.telefone)
        if not chave:
            return None
        achados = [
            c for c in Cliente.objects.exclude(celular="", telefone="").only("pk", "celular", "telefone")
            if chave in (chave_telefone(c.celular), chave_telefone(c.telefone))
        ]
        return achados[0] if len(achados) == 1 else None


class Mensagem(models.Model):
    ENTRADA, SAIDA = "entrada", "saida"
    DIRECOES = [(ENTRADA, "Recebida"), (SAIDA, "Enviada")]
    CONTATO, ROBO, EQUIPE = "contato", "robo", "equipe"
    AUTORES = [(CONTATO, "Contato"), (ROBO, "Robô"), (EQUIPE, "Equipe")]

    conversa = models.ForeignKey(Conversa, on_delete=models.CASCADE, related_name="mensagens")
    direcao = models.CharField("direção", max_length=7, choices=DIRECOES)
    autor = models.CharField(max_length=7, choices=AUTORES)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    tipo = models.CharField(max_length=20, default="text")
    texto = models.TextField(blank=True)
    arquivo = models.FileField(upload_to="whatsapp/%Y/%m/", blank=True)
    nome_arquivo = models.CharField(max_length=200, blank=True)
    wa_id = models.CharField("ID no WhatsApp", max_length=128, unique=True, null=True, blank=True)
    erro = models.CharField(max_length=300, blank=True, help_text="Motivo, se o envio falhou")
    criada_em = models.DateTimeField("criada em", default=timezone.now)

    class Meta:
        ordering = ["criada_em", "pk"]
        verbose_name = "mensagem"
        verbose_name_plural = "mensagens"

    def __str__(self):
        return f"{self.get_autor_display()}: {self.texto[:60]}"

    @property
    def descricao_arquivo(self):
        return self.nome_arquivo or (self.arquivo.name.rsplit("/", 1)[-1] if self.arquivo else "")


class Solicitacao(Registro):
    AGENDAMENTO, DOCUMENTOS, ATENDENTE = "agendamento", "documentos", "atendente"
    TIPOS = [
        (AGENDAMENTO, "Pedido de agendamento"),
        (DOCUMENTOS, "Documentos solicitados"),
        (ATENDENTE, "Falar com a equipe"),
    ]

    conversa = models.ForeignKey(Conversa, on_delete=models.CASCADE, related_name="solicitacoes")
    tipo = models.CharField(max_length=12, choices=TIPOS)
    resumo = models.CharField(max_length=250)
    detalhes = models.TextField(blank=True)
    resolvida = models.BooleanField(default=False)
    resolvida_em = models.DateTimeField("resolvida em", null=True, blank=True)
    resolvida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="resolvida por", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["resolvida", "-criado_em"]
        verbose_name = "solicitação"
        verbose_name_plural = "solicitações"

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.resumo}"

    def get_absolute_url(self):
        return self.conversa.get_absolute_url()
