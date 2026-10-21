# CLAUDE.md — regras permanentes do Personal Wealth Manager

Aplicação local e offline (FastAPI + SQLite + Jinja2) para acompanhar o património pessoal.
O dono do projeto não é programador experiente: explica as decisões técnicas em poucas linhas,
em português europeu, e diz sempre o impacto prático.

O projeto é acompanhado noutra conta Claude (claude.ai) que lê este repositório via GitHub.
O que não estiver no repositório (ou no `estado-projeto.md`, que fica fora do Git) essa conta não sabe.
Por isso, cada decisão relevante fica escrita em `docs/registo-tecnico.md`.

## Início da sessão
1. Clonar o repositório ou, se já existir, `git pull --ff-only`.
2. Ler este ficheiro e `docs/registo-tecnico.md`.
3. Correr `pytest` e dizer quantos testes passam antes de mexer em código.
4. Ler o `estado-projeto.md` da última sessão (entregue pelo dono, fora do Git).

## Durante a sessão
- Commits pequenos, com mensagens descritivas, um tema por commit.
- Testes a passar antes de cada commit. Código novo leva testes novos.
- Valores nos testes e na demo (`scripts/seed_demo.py`) são sempre fictícios.
- Nunca incluir no Git: `*.db`, `data/`, `backup/`, `scripts/seed_pessoal.py`, `estado-projeto.md`,
  nomes da família, nomes de bancos reais associados a contas reais, valores reais.
  Antes de cada push: `git status --short` e um grep aos ficheiros em stage.
- Dinheiro em cêntimos inteiros (`int`), nunca `float`.
- A base de dados fica fora do OneDrive (`db.connect` recusa caminhos com "onedrive").
- Não inventar. O que não foi verificado escreve-se como "por confirmar".
- Mudanças de esquema: subir `SCHEMA_VERSION` em `app/db.py`, migração automática em `init_db`
  (via `_migrar`), testes de migração em `tests/test_migracao.py`, e rever `backup.TABELAS`
  e `restauro.TABELAS_OPCIONAIS` / `COLUNAS_OPCIONAIS` para cópias antigas continuarem a restaurar.
- Não mexer na pasta do OneDrive nem na base de dados real. Esse teste é feito pelo dono,
  no outro computador, com `git pull --ff-only`.

## Fim da sessão (por esta ordem)
1. Todos os testes a passar; dizer o número.
2. Commit e push para `main`.
3. Atualizar `docs/registo-tecnico.md`: o que mudou, ficheiros, decisões, esquema.
4. Gerar o `estado-projeto.md` novo (fora do Git), com a estrutura de secções atual
   (objetivo, decisões, plataformas, dashboard, riscos, próximos passos, histórico), incluindo:
   hash do último commit e número de testes; separação entre o verificado (testes, ecrã, código lido)
   e o que ficou por confirmar; uma linha nova no histórico com título em kebab-case;
   próximos passos atualizados. Entregar num bloco de código ou ficheiro para download.

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
