# CLAUDE.md — regras permanentes do Personal Wealth Manager

Aplicação local e offline (FastAPI + SQLite + Jinja2) para acompanhar o património pessoal.
O dono do projeto não é programador experiente: explica as decisões técnicas em poucas linhas,
em português europeu, e diz sempre o impacto prático. Quando ele tiver de agir no PowerShell,
dá os comandos um a um, prontos a colar, e diz o que deve aparecer.

## Modelo de trabalho (desde 21/10/2026)
- **O Claude Code é o responsável principal** pela arquitetura e pela programação.
- **Desenvolvimento:** num clone do GitHub na cloud, onde corre o Git e o `pytest`. Commit e push para `main`.
- **GitHub (`main`) é a fonte da verdade** do código.
- **Computador do dono (Windows, Python 3.14):** é onde a app corre com os dados reais. A pasta do projeto
  é um clone Git que só recebe `git pull --ff-only`. **Nunca escrever ficheiros rastreados pelo Git nessa
  pasta** (o pull deixa de funcionar). O único ficheiro que o Claude lá escreve é o `estado-projeto.md`
  (no `.gitignore`), através da ligação ao computador.
- O que for específico do Windows (`scripts/pwm.bat`, `%LOCALAPPDATA%`, a base real) só se confirma no
  computador do dono: fica "por confirmar" até ele o ver.
- Outras contas ou sessões podem ler o repositório: cada decisão relevante fica em `docs/registo-tecnico.md`.

## Início da sessão
1. Clonar o repositório ou, se já existir, `git pull --ff-only`.
2. Ler este ficheiro e `docs/registo-tecnico.md`.
3. Correr `pytest` e dizer quantos testes passam antes de mexer em código.
4. Ler o `estado-projeto.md` na pasta do projeto do computador do dono (pela ligação ao computador).
   Se a ligação não estiver disponível, pedir-lhe o ficheiro em anexo.

## Durante a sessão
- Commits pequenos, com mensagens descritivas, um tema por commit.
- Testes a passar antes de cada commit. Código novo leva testes novos.
- Valores nos testes e na demo (`scripts/seed_demo.py`) são sempre fictícios.
- Nunca incluir no Git: `*.db`, `data/`, `backup/`, `scripts/seed_pessoal.py`, `estado-projeto.md`,
  nomes da família, nomes de bancos reais associados a contas reais, valores reais.
  Antes de cada push: `git status --short` e um grep aos ficheiros em stage.
- Dinheiro em cêntimos inteiros (`int`), nunca `float`.
- A base de dados fica fora de pastas sincronizadas (`db.connect` recusa caminhos com "onedrive").
  Por defeito: `%LOCALAPPDATA%\pwm\pwm.db`.
- Não inventar. O que não foi verificado escreve-se como "por confirmar".
- Mudanças de esquema: subir `SCHEMA_VERSION` em `app/db.py`, migração automática em `init_db`
  (via `_migrar`), testes de migração em `tests/test_migracao.py`, e rever `backup.TABELAS`
  e `restauro.TABELAS_OPCIONAIS` / `COLUNAS_OPCIONAIS` para cópias antigas continuarem a restaurar.
- Nunca tocar na base de dados real nem nas pastas `backup\` do dono. Mudanças de esquema chegam
  à base real pela migração automática, no arranque, depois do `git pull`.

## Fim da sessão (por esta ordem)
1. Todos os testes a passar; dizer o número.
2. Commit e push para `main`.
3. Atualizar `docs/registo-tecnico.md`: o que mudou, ficheiros, decisões, esquema.
4. Atualizar o `estado-projeto.md` na pasta do projeto do dono, com a estrutura de secções atual
   (objetivo, decisões, plataformas, dashboard, riscos, próximos passos, histórico), incluindo:
   hash do último commit e número de testes; separação entre o verificado (testes, ecrã, código lido)
   e o que ficou por confirmar; uma linha nova no histórico com título em kebab-case;
   próximos passos atualizados. Sem ligação ao computador: entregar como ficheiro para download.
5. Dizer ao dono os comandos para atualizar o computador (`git pull --ff-only` e, se mudarem as
   dependências, `pip install -r requirements.txt` no venv).

## Mapa rápido do código
- `app/db.py` — esquema, versão (`PRAGMA user_version`), migrações, regra do OneDrive.
- `app/calc.py` — conversão euros↔cêntimos, ganho do mês, formatação de meses.
- `app/checkin.py` — check-in mensal (saldos, aportes, data da leitura).
- `app/planos.py` — Desafio das 52 semanas e sugestões de aporte.
- `app/plataformas.py` — gestão de plataformas (criar, editar, desativar, apagar).
- `app/dashboard.py` — painel (património, evolução, alocação, cobertura do fundo de liberdade).
- `app/configuracao.py` — valores editáveis guardados na base (despesa mensal de referência).
- `app/backup.py` / `app/restauro.py` — cópias CSV com data e hora, e restauro.
- `app/main.py` — rotas web e middleware que só aceita pedidos locais.
- `scripts/pwm.bat` — arranque no Windows (venv em `%LOCALAPPDATA%\pwm\venv`, backup, abre o browser).
