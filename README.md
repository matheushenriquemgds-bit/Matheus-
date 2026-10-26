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

## Colocando em produção

Configure as variáveis de ambiente (modelo em `.env.example`):

| Variável | Para quê |
|---|---|
| `DEBUG` | `False` em produção |
| `SECRET_KEY` | chave longa e aleatória |
| `ALLOWED_HOSTS` | domínio(s) do sistema, ex.: `sistema.meuescritorio.com.br` |
| `CSRF_TRUSTED_ORIGINS` | ex.: `https://sistema.meuescritorio.com.br` |
| `DATABASE_URL` | ex.: `postgres://usuario:senha@host:5432/banco` (sem ela, usa SQLite) |

Depois rode:

```bash
pip install -r requirements.txt "psycopg[binary]"   # psycopg só se usar PostgreSQL
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi --bind 0.0.0.0:8000
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
