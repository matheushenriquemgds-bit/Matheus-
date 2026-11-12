"""O robô de atendimento: monta a conversa, chama o Claude e executa as ações que ele pede."""

import json
import logging

import anthropic
from django.conf import settings
from django.utils import timezone

from .models import Configuracao, Mensagem, Solicitacao

log = logging.getLogger(__name__)

MAX_MENSAGENS_HISTORICO = 40
MAX_RODADAS_FERRAMENTAS = 5

RESPOSTA_ERRO = (
    "Desculpe, tive um problema para responder agora. Já avisei a equipe do escritório e alguém vai "
    "falar com você em breve."
)

INSTRUCOES = """Você é o assistente virtual de {escritorio}, um escritório de advocacia, e atende os contatos \
pelo WhatsApp. Você não é advogado: seu papel é receber as pessoas, tirar dúvidas gerais sobre o escritório, \
registrar pedidos de agendamento e pedir documentos. A equipe do escritório acompanha tudo pelo sistema.

## O que você faz
1. Dúvidas sobre o escritório: responda só com base nas INFORMAÇÕES DO ESCRITÓRIO abaixo. Se a resposta não \
estiver lá, diga que vai verificar com a equipe e use transferir_para_equipe.
2. Agendamento: descubra o nome da pessoa, o assunto em poucas palavras e os dias e horários que ela prefere \
(e se prefere presencial, por vídeo ou por telefone, quando o escritório oferecer opções). Então use \
registrar_pedido_de_agendamento. Você não tem acesso à agenda: nunca confirme data ou horário. Diga que a \
equipe vai confirmar o horário por aqui.
3. Documentos: quando o caso da pessoa exigir documentos, consulte a lista DOCUMENTOS POR TIPO DE CASO, \
explique quais enviar e use registrar_pedido_de_documentos. Peça que ela envie fotos legíveis ou PDFs por aqui \
mesmo. Quando chegarem arquivos, agradeça e diga quais itens da lista ainda faltam, pelo nome dos arquivos.

## Regras
- Não dê opinião jurídica sobre o caso da pessoa, não diga se ela "tem direito" ou "vai ganhar", não estime \
valores de causa nem prazos do processo e não prometa resultados. Pode explicar de forma geral o que o \
escritório faz. Para perguntas sobre o caso, diga que o advogado vai analisar e ofereça o agendamento.
- Você não tem acesso a processos. Nunca informe andamento, número ou detalhes de processos, mesmo que a \
pessoa diga ser cliente; use transferir_para_equipe.
- Use transferir_para_equipe também quando a pessoa pedir para falar com alguém, quando for urgente \
(prisão, audiência ou prazo para hoje ou amanhã, violência, risco à saúde), quando ela estiver muito \
insatisfeita ou quando você não souber ajudar. Depois disso, avise que a equipe vai responder por aqui.
- Peça apenas os dados necessários. Não peça senhas, dados de cartão ou dados bancários.
- Você não consegue ouvir áudios nem ver vídeos. Se receber um, peça com educação que a pessoa escreva.
- Não invente informações. Não fale de outros clientes.

## Estilo
- Português do Brasil, tom cordial e profissional, tratando a pessoa por "você".
- Mensagens curtas, como numa conversa de WhatsApp: no máximo uns 3 parágrafos curtos. Uma pergunta por vez.
- Para destacar, use *negrito* do WhatsApp. Não use títulos, tabelas nem links em Markdown.
- Na primeira mensagem da conversa, apresente-se como assistente virtual do escritório.

## INFORMAÇÕES DO ESCRITÓRIO
{informacoes}

## DOCUMENTOS POR TIPO DE CASO
{documentos}"""

DOCUMENTOS_PADRAO = "Não definida. Peça documento de identidade com foto (RG ou CNH) e comprovante de residência."

FERRAMENTAS = [
    {
        "name": "registrar_pedido_de_agendamento",
        "description": "Registra um pedido de agendamento de consulta/reunião para a equipe confirmar. "
                       "Use quando já souber o nome, o assunto e a preferência de dias e horários.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome completo informado pela pessoa"},
                "assunto": {"type": "string", "description": "Assunto em poucas palavras, ex.: 'aposentadoria'"},
                "preferencia": {"type": "string", "description": "Dias e horários preferidos, como a pessoa disse"},
                "modalidade": {"type": "string", "enum": ["presencial", "video", "telefone", "sem preferencia"]},
                "observacoes": {"type": "string", "description": "Outras informações úteis, ou vazio"},
            },
            "required": ["nome", "assunto", "preferencia", "modalidade", "observacoes"],
            "additionalProperties": False,
        },
    },
    {
        "name": "registrar_pedido_de_documentos",
        "description": "Registra quais documentos foram pedidos à pessoa, para a equipe acompanhar o envio.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "documentos": {"type": "array", "items": {"type": "string"}, "description": "Documentos pedidos"},
                "finalidade": {"type": "string", "description": "Para que servem, ex.: 'ação de aposentadoria'"},
            },
            "required": ["documentos", "finalidade"],
            "additionalProperties": False,
        },
    },
    {
        "name": "transferir_para_equipe",
        "description": "Passa a conversa para uma pessoa da equipe. Depois disso o robô para de responder "
                       "este contato até a equipe devolver a conversa.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {"type": "string", "description": "Por que a equipe precisa assumir, em uma frase"},
                "urgente": {"type": "boolean", "description": "true se houver urgência"},
            },
            "required": ["motivo", "urgente"],
            "additionalProperties": False,
        },
    },
]


def _cliente_api():
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None)


def instrucoes(config):
    return INSTRUCOES.format(
        escritorio=config.nome_escritorio,
        informacoes=config.informacoes.strip() or "Nenhuma informação cadastrada. Para qualquer dúvida sobre o "
                                                  "escritório, diga que vai verificar com a equipe.",
        documentos=config.documentos.strip() or DOCUMENTOS_PADRAO,
    )


def _contexto(conversa):
    agora = timezone.localtime()
    linhas = [f"Data e hora atuais: {agora:%d/%m/%Y %H:%M} (horário de Brasília)."]
    if conversa.nome:
        linhas.append(f"Nome do contato no perfil do WhatsApp: {conversa.nome}.")
    if conversa.cliente_id:
        linhas.append(f"Este número está cadastrado como cliente do escritório: {conversa.cliente}.")
    return " ".join(linhas)


def _conteudo(m):
    if m.autor == Mensagem.CONTATO:
        if m.tipo in ("audio", "video"):
            return f"[O contato enviou um {'áudio' if m.tipo == 'audio' else 'vídeo'}]" + (f" {m.texto}" if m.texto else "")
        if m.arquivo or m.tipo in ("document", "image"):
            nome = m.descricao_arquivo or m.tipo
            return f"[O contato enviou o arquivo: {nome}]" + (f" Legenda: {m.texto}" if m.texto else "")
        return m.texto or f"[Mensagem do tipo {m.tipo}]"
    if m.autor == Mensagem.EQUIPE:
        return f"[Mensagem escrita por uma pessoa da equipe] {m.texto}"
    return m.texto


def historico(conversa):
    """Últimas mensagens no formato da API, começando sempre por uma mensagem do contato."""
    mensagens = list(conversa.mensagens.exclude(erro__gt="").order_by("-criada_em", "-pk")[:MAX_MENSAGENS_HISTORICO])
    mensagens.reverse()
    while mensagens and mensagens[0].direcao != Mensagem.ENTRADA:
        mensagens.pop(0)
    saida = []
    for m in mensagens:
        papel = "user" if m.direcao == Mensagem.ENTRADA else "assistant"
        texto = _conteudo(m).strip() or "…"
        if saida and saida[-1]["role"] == papel:
            saida[-1]["content"] += "\n\n" + texto
        else:
            saida.append({"role": papel, "content": texto})
    return saida


def _executar(conversa, nome, dados):
    """Executa uma ferramenta pedida pelo modelo e devolve o texto do resultado."""
    if nome == "registrar_pedido_de_agendamento":
        Solicitacao.objects.create(
            conversa=conversa,
            tipo=Solicitacao.AGENDAMENTO,
            resumo=f"{dados['nome']} — {dados['assunto']}"[:250],
            detalhes="\n".join([
                f"Nome: {dados['nome']}",
                f"Assunto: {dados['assunto']}",
                f"Preferência: {dados['preferencia']}",
                f"Modalidade: {dados['modalidade']}",
            ] + ([f"Observações: {dados['observacoes']}"] if dados.get("observacoes") else [])),
        )
        return "Pedido registrado. Diga à pessoa que a equipe vai confirmar o horário por aqui."
    if nome == "registrar_pedido_de_documentos":
        docs = [d for d in dados.get("documentos", []) if d.strip()]
        Solicitacao.objects.create(
            conversa=conversa,
            tipo=Solicitacao.DOCUMENTOS,
            resumo=f"{dados.get('finalidade') or 'Documentos'}: {', '.join(docs)}"[:250],
            detalhes="\n".join(f"- {d}" for d in docs),
        )
        return "Pedido de documentos registrado. Os arquivos enviados aqui ficam salvos para a equipe."
    if nome == "transferir_para_equipe":
        transferir(conversa, dados.get("motivo", ""), dados.get("urgente", False))
        return "Conversa transferida. Avise a pessoa que alguém da equipe vai responder por aqui."
    raise ValueError(f"Ferramenta desconhecida: {nome}")


def transferir(conversa, motivo, urgente=False):
    conversa.bot_pausado = True
    conversa.save(update_fields=["bot_pausado", "atualizado_em"])
    Solicitacao.objects.create(
        conversa=conversa,
        tipo=Solicitacao.ATENDENTE,
        resumo=(("URGENTE: " if urgente else "") + (motivo or "Pediu para falar com a equipe"))[:250],
    )


def gerar_resposta(conversa):
    """Chama o Claude com o histórico da conversa e devolve o texto a enviar (ou "" se não houver)."""
    config = Configuracao.atual()
    mensagens = historico(conversa)
    if not mensagens or mensagens[-1]["role"] != "user":
        return ""
    # O contexto que muda a cada conversa vai numa mensagem de sistema no fim, para não invalidar o cache
    # das instruções, que são iguais para todas as conversas.
    mensagens.append({"role": "system", "content": _contexto(conversa)})
    cliente = _cliente_api()

    for _ in range(MAX_RODADAS_FERRAMENTAS):
        resposta = cliente.beta.messages.create(
            model=settings.BOT_MODELO,
            max_tokens=4000,
            system=instrucoes(config),
            messages=mensagens,
            tools=FERRAMENTAS,
            output_config={"effort": settings.BOT_ESFORCO},
            cache_control={"type": "ephemeral"},
            # Se o modelo principal recusar a mensagem, a API tenta de novo com outro modelo.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resposta.stop_reason == "refusal":
            log.warning("Resposta recusada na conversa %s: %s", conversa.pk, resposta.stop_details)
            transferir(conversa, "O robô não conseguiu responder a última mensagem")
            return RESPOSTA_ERRO
        if resposta.stop_reason != "tool_use":
            return "\n\n".join(b.text for b in resposta.content if b.type == "text").strip()

        resultados = []
        for bloco in resposta.content:
            if bloco.type != "tool_use":
                continue
            try:
                dados = bloco.input if isinstance(bloco.input, dict) else json.loads(bloco.input)
                resultados.append({"type": "tool_result", "tool_use_id": bloco.id,
                                   "content": _executar(conversa, bloco.name, dados)})
            except Exception as e:  # noqa: BLE001 - o erro volta para o modelo decidir o que fazer
                log.exception("Erro na ferramenta %s", bloco.name)
                resultados.append({"type": "tool_result", "tool_use_id": bloco.id,
                                   "content": f"Erro: {e}", "is_error": True})
        mensagens.append({"role": "assistant", "content": resposta.content})
        mensagens.append({"role": "user", "content": resultados})

    log.warning("Conversa %s: limite de rodadas de ferramentas atingido", conversa.pk)
    transferir(conversa, "O robô não conseguiu concluir o atendimento")
    return RESPOSTA_ERRO

