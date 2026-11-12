# Gestão Jurídica

Sistema web para escritórios de advocacia: cadastro de clientes e processos, recebimento automático de
publicações (DJEN / Comunica PJe do CNJ), controle de prazos e agenda, e financeiro.

Feito em Python/Django, com acesso por login para vários usuários.

## Funcionalidades

**Clientes**
- Pessoa física e jurídica, com documentos, contatos, endereço e observações.
- Ficha do cliente com seus processos, compromissos e lançamentos financeiros.

**Processos**
- Número CNJ formatado automaticamente e validado pelo dígito verificador; números duplicados são recusados.
- Partes, tribunal, vara, comarca, área, classe, valor da causa e advogado responsável.
- Histórico de andamentos, manual ou gerado automaticamente pelas publicações.

**Publicações**
- Cadastro das OABs a monitorar. A busca usa a API pública do CNJ
  ([Comunica PJe](https://comunicaapi.pje.jus.br/swagger/index.html)), que reúne o Diário de Justiça Eletrônico
  Nacional (DJEN).
- Cada publicação é vinculada automaticamente ao processo de mesmo número e vira um andamento.
- Caixa de entrada com lidas/não lidas, marcação em lote e o botão "Lida e próxima".
- Criação de prazo a partir da publicação, com cálculo do vencimento (veja abaixo).
- Publicações de processos ainda não cadastrados ficam marcadas como "sem processo". Ao cadastrar o
  processo depois, elas são vinculadas a ele.

**Prazos e agenda**
- Prazos, audiências, tarefas e reuniões, com responsável, processo e cliente.
- Lista com filtros (pendentes, atrasados, concluídos) e calendário mensal.
- Painel inicial com os atrasados e os próximos 7 dias.

**Financeiro**
- Receitas (honorários contratuais, de êxito, de sucumbência…) e despesas (custas, diligências…).
- Parcelamento automático em meses, marcação de pago e totais por filtro.

**Atendimento por WhatsApp (robô com IA)**
- Um assistente virtual responde os contatos no WhatsApp do escritório: tira dúvidas sobre o escritório,
  registra pedidos de agendamento e pede documentos. Ele usa o Claude, da Anthropic.
- Não dá opinião jurídica, não informa andamento de processos e não confirma horários: passa para a equipe
  quando a pessoa pede, quando é urgente ou quando não sabe responder.
- Tudo aparece em **WhatsApp** no menu: conversas, arquivos recebidos e solicitações pendentes (agendamentos,
  documentos e pedidos para falar com a equipe).
- A equipe pode assumir qualquer conversa e responder pelo próprio sistema. Enquanto isso, o robô fica pausado
  naquela conversa.
- O contato é vinculado sozinho ao cliente cujo celular estiver no cadastro.

### Como o prazo é calculado

- **Publicação:** considera-se publicada no primeiro dia útil após a disponibilização no Diário.
- **Início:** o prazo começa no dia útil seguinte (Lei 11.419/2006, art. 4º, §§ 3º e 4º).
- **Dias úteis (CPC, art. 219):** não contam fins de semana, feriados nacionais (inclusive Carnaval, Sexta-feira
  Santa e Corpus Christi) nem o recesso de 20/12 a 20/01 (art. 220).
- **Feriados locais:** cadastre-os em *Administração → Feriados* para que entrem na conta.

> Sempre confira a data calculada com o calendário do tribunal (suspensões de expediente, feriados locais etc.).

## Como rodar

Requisito: Python 3.11 ou mais recente.

```bash
python -m venv .venv
source .venv/bin/activate          # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # cria o primeiro usuário (administrador)
python manage.py runserver
```

Acesse http://localhost:8000 e entre com o usuário criado.

Para ver o sistema já preenchido com exemplos, rode `python manage.py dados_demo`. O comando só funciona
com o banco vazio.

### Usuários da equipe

Em **Administração → Usuários**, crie um usuário para cada pessoa do escritório. Marque "Membro da equipe"
para quem também deve acessar a área de administração.

### Busca automática de publicações

1. Em **Publicações → OABs monitoradas**, cadastre o número e a UF de cada advogado.
2. Para buscar na hora, use **Buscar agora** na tela de publicações.
3. Para buscar sozinho, agende o comando no servidor. Exemplo com cron (dias úteis, às 7h, 13h e 19h):

   ```
   0 7,13,19 * * 1-5  cd /caminho/do/projeto && .venv/bin/python manage.py buscar_publicacoes
   ```

   Para um período específico: `python manage.py buscar_publicacoes --inicio 2026-10-01 --fim 2026-10-15`.

Na primeira busca de cada OAB, o sistema olha os últimos 7 dias (`PUBLICACOES_DIAS_INICIAIS`). Nas
seguintes, continua de onde parou.

## Robô do WhatsApp

Usa a **WhatsApp Cloud API**, a forma oficial da Meta. Para testar não é preciso chip: a Meta oferece um
número de teste gratuito, que conversa com até 5 números cadastrados por você.

### 1. Escrever o que o robô pode dizer

Entre no sistema, vá em **WhatsApp → Configurar robô** e preencha:

- **Informações do escritório:** endereço, horário, áreas de atuação, como funciona a primeira consulta,
  formas de pagamento. O robô não informa nada que não esteja aqui.
- **Documentos por tipo de caso:** por exemplo, "Aposentadoria: RG, CPF, carteira de trabalho, CNIS".

### 2. Testar o robô no terminal (sem WhatsApp)

Crie uma chave em [platform.claude.com](https://platform.claude.com) (Settings → API keys) e rode:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python manage.py conversar_robo
```

Você escreve como se fosse o cliente e vê as respostas. Os pedidos registrados aparecem no sistema, na
conversa "Teste pelo terminal". Use `--nova` para começar uma conversa do zero.

### 3. Criar o app na Meta

1. Em [developers.facebook.com](https://developers.facebook.com), entre com seu Facebook e clique em
   **Meus apps → Criar app**. Escolha o caso de uso de **WhatsApp** (conectar-se com clientes pelo WhatsApp).
2. No painel do app, abra **WhatsApp → Configuração da API**. Ali estão:
   - o **número de teste** e a **Identificação do número de telefone** (`WHATSAPP_PHONE_NUMBER_ID`);
   - o botão para gerar o **token de acesso** (`WHATSAPP_TOKEN`). Esse token vence em 24 horas e serve só
     para testar (veja o passo 6 para um permanente);
   - o campo **Para**, onde você cadastra o seu WhatsApp pessoal e confirma com o código recebido.
3. Em **Configurações do app → Básico**, copie a **Chave secreta do aplicativo** (`WHATSAPP_APP_SECRET`).
4. Invente uma senha qualquer para `WHATSAPP_VERIFY_TOKEN`.

### 4. Colocar o sistema no ar

A Meta precisa conseguir acessar o sistema por um endereço `https://`. Coloque-o em produção (seção
abaixo) com as variáveis do WhatsApp e a `ANTHROPIC_API_KEY`.

> Os arquivos recebidos ficam em `MEDIA_ROOT`. Em serviços como Render e Railway, o disco é apagado a cada
> nova versão: crie um volume (disco persistente) e aponte `MEDIA_ROOT` para ele.

O robô responde em segundo plano dentro do próprio servidor. Rode o gunicorn com **um processo** e várias
threads (`--workers 1 --threads 8`) para que duas mensagens seguidas do mesmo contato não sejam respondidas
em dobro.

### 5. Ligar o webhook

1. No painel da Meta, abra **WhatsApp → Configuração** e, em **Webhook**, clique em **Editar**.
2. **URL de callback:** `https://seu-dominio/whatsapp/webhook/`.
   **Token de verificação:** o mesmo valor de `WHATSAPP_VERIFY_TOKEN`.
3. Em **Campos do webhook**, assine **messages**.
4. Do seu WhatsApp, mande uma mensagem para o número de teste. A conversa aparece em **WhatsApp** no
   sistema e o robô responde.

### 6. Usar de verdade

- **Token permanente:** em [business.facebook.com](https://business.facebook.com) → Configurações →
  Usuários do sistema, crie um usuário do sistema com acesso ao app e gere um token com as permissões
  `whatsapp_business_messaging` e `whatsapp_business_management`.
- **Número do escritório:** em **WhatsApp → Configuração da API**, adicione um número de telefone real
  (pode ser fixo). Ele não pode estar em uso no aplicativo do WhatsApp; se estiver, apague a conta do app
  antes. Depois troque `WHATSAPP_PHONE_NUMBER_ID` pelo ID do novo número.
- **Custos:** responder quem escreveu para o escritório não é cobrado pela Meta dentro de 24 horas.
  A IA é cobrada pela Anthropic por uso; acompanhe em platform.claude.com.
- **Regra das 24 horas:** o WhatsApp só deixa mandar mensagem livre até 24 h depois da última mensagem do
  contato. Depois disso, é preciso esperar ele escrever de novo.

## Colocando em produção

Configure as variáveis de ambiente (modelo em `.env.example`):

| Variável | Para quê |
|---|---|
| `DEBUG` | `False` em produção |
| `SECRET_KEY` | chave longa e aleatória |
| `ALLOWED_HOSTS` | domínio(s) do sistema, ex.: `sistema.meuescritorio.com.br` |
| `CSRF_TRUSTED_ORIGINS` | ex.: `https://sistema.meuescritorio.com.br` |
| `DATABASE_URL` | ex.: `postgres://usuario:senha@host:5432/banco` (sem ela, usa SQLite) |
| `ANTHROPIC_API_KEY` | chave da API do Claude, para o robô do WhatsApp |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | token e ID do número, do painel da Meta |
| `WHATSAPP_APP_SECRET` | chave secreta do app da Meta (confere que os avisos vêm mesmo da Meta) |
| `WHATSAPP_VERIFY_TOKEN` | senha que você inventa e repete na configuração do webhook |
| `MEDIA_ROOT` | pasta dos arquivos recebidos pelo WhatsApp (use um disco persistente) |
| `BOT_MODELO`, `BOT_ESFORCO` | opcionais: modelo do Claude (`claude-opus-5-5`) e esforço (`low`, `medium`, `high`) |

Depois rode:

```bash
pip install -r requirements.txt "psycopg[binary]"   # psycopg só se usar PostgreSQL
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 1 --threads 8
```

Funciona em qualquer serviço que rode Python, como Railway, Render, Fly.io ou uma VPS. Use HTTPS e
faça backup do banco de dados.

## Desenvolvimento

```bash
python manage.py test
```

Estrutura dos módulos:

| Pasta | Conteúdo |
|---|---|
| `core/` | painel, utilidades (número CNJ, dias úteis, feriados), telas genéricas |
| `clientes/` | cadastro de clientes |
| `processos/` | processos e andamentos |
| `publicacoes/` | OABs monitoradas, publicações e integração com o CNJ (`servicos.py`) |
| `agenda/` | prazos, audiências, tarefas e calendário |
| `financeiro/` | receitas e despesas |
| `whatsapp/` | robô de atendimento: webhook e envio (`api.py`, `servico.py`), IA (`bot.py`), conversas e solicitações |
