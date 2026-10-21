# Registo técnico

Histórico das alterações relevantes ao código, uma entrada por commit (ou por sessão).
Serve para quem lê o repositório sem ter estado na sessão perceber o que mudou e porquê.
O que não foi verificado está marcado como "por confirmar".

Versão atual do esquema da base: **3** (`SCHEMA_VERSION` em `app/db.py`).

| Versão | Mudança | Migração |
|---|---|---|
| 1 | Tabelas `plataformas`, `registos_mensais`, `planos` | — |
| 2 | Coluna `registos_mensais.data_leitura` (AAAA-MM-DD, pode ser NULL) | `ALTER TABLE` em `_migrar` |
| 3 | Tabela `configuracao (chave TEXT PK, valor INTEGER)` | `CREATE TABLE IF NOT EXISTS` no arranque |

---

## 0e71688 — Revisão: limites de valores e caminho da base resolvido
19/10/2026 · 324 testes (+9)

**O que mudou**
- `calc.euros_para_cent` recusa valores acima de 10 mil milhões de euros (`LIMITE_CENT = 10**12`).
  Antes, um número gigante passava a validação e rebentava no SQLite com `OverflowError` (erro 500).
- `plataformas.validar` limita o campo "ordem" a ±1.000.000, pelo mesmo motivo.
- `db.connect` passa o caminho por `expanduser().resolve()` antes de verificar a regra do OneDrive.
  Um `PWM_DB` relativo (ex.: `pwm.db`) corrido dentro da pasta do projeto, ou uma ligação simbólica,
  apontava para o OneDrive sem a palavra aparecer no texto e escapava à regra.
- `restauro` recusa inteiros fora do intervalo do SQLite (±2^63) com `ValueError` legível.

**Ficheiros:** `app/calc.py`, `app/db.py`, `app/plataformas.py`, `app/restauro.py`;
testes em `test_calc.py`, `test_db.py`, `test_main.py`, `test_plataformas.py`, `test_restauro.py`.

**Decisões:** limites altos o suficiente para nunca incomodar um património real e baixos o suficiente
para nunca chegar ao limite do SQLite. Erros de validação em vez de erro 500.

**Esquema:** sem alterações (continua na versão 3).

---

## 09a5111 — v2: cobertura do fundo de liberdade no painel
19/10/2026 · 315 testes (+25)

**O que mudou**
- Nova tabela `configuracao` (chave/valor inteiro) para valores editáveis na app.
- Novo módulo `app/configuracao.py` com a despesa mensal de referência (em cêntimos).
  Campo em branco apaga a referência; 0 ou negativo é recusado.
- Painel: nova caixa "Fundo de liberdade" com a cobertura em meses =
  saldo da categoria `emergencia` no mês do painel ÷ despesa mensal de referência.
  O campo da referência edita-se no próprio painel (`POST /configuracao/despesa-mensal`),
  e cada gravação faz cópia de segurança.
- `backup.TABELAS` passa a incluir `configuracao` (novo `configuracao.csv` em cada cópia).
- `restauro` aceita cópias antigas sem `configuracao.csv` (`TABELAS_OPCIONAIS`): a tabela fica vazia.
- `seed_demo` com uma referência fictícia; README atualizado.

**Ficheiros:** `README.md`, `app/backup.py`, `app/configuracao.py` (novo), `app/dashboard.py`, `app/db.py`,
`app/main.py`, `app/restauro.py`, `app/static/css/pwm.css`, `app/templates/dashboard.html`,
`scripts/seed_demo.py`; testes em `test_configuracao.py` (novo), `test_dashboard.py`, `test_db.py`,
`test_migracao.py`, `test_restauro.py`.

**Decisões**
- A despesa de referência fica na base de dados e não no código: é um dado pessoal, o repositório é público,
  e assim entra nas cópias de segurança como o resto.
- A tabela `configuracao` não tem `CHECK` na chave: uma chave nova não obriga a refazer a tabela.
  As chaves válidas vivem em `configuracao.py`.
- A cobertura usa a mesma regra do património: plataformas desativadas contam até ao último registo.
  O valor em meses é `float` só para mostrar (uma casa decimal); os valores guardados são cêntimos.
- Sem referência definida, o painel mostra só o saldo do fundo. Sem nenhuma plataforma na categoria
  `emergencia`, a caixa não aparece.

**Esquema:** **subiu de 2 para 3.** Migração: a tabela é criada pelo `CREATE TABLE IF NOT EXISTS`
do esquema no arranque (`init_db`); bases v2 abrem sem perder dados. Testado em `test_migracao.py`.

---

## 18c28e5 — Design: barra lateral, estilo comum e tipo de letra local; README com capturas
19/10/2026 · 290 testes (+7)

**O que mudou**
- `base.html` novo, partilhado pelos ecrãs: navegação lateral (vira barra no topo em janelas estreitas)
  e um único botão "Guardar e sair".
- `app/static/css/pwm.css`: estilo comum dos quatro ecrãs; azul-petróleo como cor de ação.
- Tipo de letra IBM Plex Sans guardado localmente (licença OFL 1.1 incluída); números tabulares.
- Painel: resumo do património, gráficos em caixas, plataformas numa lista agrupada por categoria
  (subtotal só com mais de uma conta); legenda do donut com valor e percentagem.
- Check-in: barra de gravação fixa no fundo; tabela empilhada em janelas estreitas.
- README com estado atualizado e capturas da demonstração em `docs/capturas/`.
- `tests/test_layout.py`: navegação, estilo, fontes locais e nenhum recurso externo.

**Ficheiros:** `README.md`, `app/static/css/pwm.css` (novo), `app/static/vendor/fonts/*` (novos),
`app/templates/base.html` (novo), `checkin.html`, `dashboard.html`, `plataformas.html`, `sair.html`,
`docs/capturas/*.png` (novos), `tests/test_layout.py` (novo).

**Decisões:** tudo local (fontes e CSS), nada de CDN, para a app continuar a funcionar offline.
As capturas usam os dados fictícios da demo (por confirmar visualmente que não há dados reais nas imagens;
as imagens não foram abertas nesta revisão).

**Esquema:** sem alterações (versão 2).

---

## 8a4a9dc — Ajustes da demo: fundo de liberdade, meses MM-AAAA, desafio por mês, aviso ao sair
19/10/2026 · 283 testes (+12)

**O que mudou**
- A categoria interna `emergencia` passa a aparecer no ecrã como "Fundo de liberdade"
  (antes "Fundo de emergência"). O código guardado na base não mudou.
- Check-in mostra o nome da categoria em vez do código (filtro `categoria` no Jinja).
- Meses no ecrã em MM-AAAA (novo `calc.formatar_mes`); dados e formulários continuam em AAAA-MM.
- Desafio das 52 semanas no check-in agrupado por mês (`planos.Sugestao.por_mes`, `GrupoMes`),
  com o detalhe das semanas ao clicar.
- Plano mensal 0 aparece como "—" em /plataformas.
- Donut sem a legenda do Chart.js (fica a lista por baixo).
- "Guardar e sair" no check-in pede confirmação se houver valores escritos e ainda não gravados.

**Ficheiros:** `app/calc.py`, `app/checkin.py`, `app/dashboard.py`, `app/main.py`, `app/planos.py`,
`app/plataformas.py`, `app/templates/checkin.html`, `dashboard.html`, `plataformas.html`, `scripts/seed_demo.py`;
testes em `test_calc.py`, `test_dashboard.py`, `test_main_plano.py`, `test_planos.py`.

**Decisões:** mudar só o rótulo, não o código interno, evita migrar dados e mantém as cópias antigas compatíveis.
O formato do mês muda só na apresentação para não mexer em validações nem na ordenação (AAAA-MM ordena bem como texto).

**Esquema:** sem alterações (versão 2).

---

## Dúvidas respondidas (revisão retroativa de 21/10/2026)

### `app/configuracao.py`: o que guarda e onde?
Guarda **apenas a despesa mensal de referência**, em cêntimos inteiros, na chave `despesa_mensal_cent`.
Fica na **base de dados SQLite**, tabela `configuracao` (a mesma base de tudo o resto, por defeito
`%LOCALAPPDATA%\pwm\pwm.db`, fora do OneDrive). Não há ficheiro de configuração no disco nem valor no código.
Entra nas cópias de segurança como `configuracao.csv`. Verificado: código lido e testes em `test_configuracao.py`.

### Há ligação entre o fundo de liberdade e a categoria "Fundo de emergência"?
Sim: **são a mesma coisa**. "Fundo de liberdade" é o rótulo de ecrã da categoria interna `emergencia`,
que antes do commit 8a4a9dc se chamava "Fundo de emergência" no ecrã. Não existe uma categoria separada.
A cobertura do painel (09a5111) soma todas as plataformas com categoria `emergencia`
(`dashboard.CATEGORIA_FUNDO`). Consequência prática: qualquer conta classificada como fundo de liberdade
entra no cálculo da cobertura; se um dia se quiser distinguir "emergência" de "liberdade", é preciso uma
categoria nova (mudança de `CHECK` no esquema, logo migração).

### O que mudou em "aviso ao sair"?
- **8a4a9dc:** o botão "Guardar e sair" do check-in ganhou um aviso (`confirm` no browser) quando há
  valores de saldo ou aporte escritos que ainda não foram gravados. Motivo: "Guardar e sair" faz a cópia
  de segurança e fecha a app, mas **não grava o check-in**, e os valores perdiam-se sem aviso.
- **18c28e5:** o botão passou para a barra lateral (`base.html`, um só em toda a app). O script do check-in
  continua ligado ao mesmo formulário (`id="form-sair"`), por isso o aviso mantém-se.
- Limites: o aviso só existe no ecrã de check-in. No formulário de plataformas e no campo da despesa
  mensal do painel não há aviso. O teste (`test_main_plano.py`) confirma que o script está na página,
  mas não executa JavaScript: o comportamento no browser está **por confirmar** no ecrã.

### Porque é que o backup de 20/10 criou uma cópia nova?
A cópia de segurança só cria uma pasta nova se o conteúdo for diferente da última cópia
(`backup._igual` compara ficheiro a ficheiro). O commit 09a5111 acrescentou `configuracao.csv` às cópias.
A última cópia anterior (feita com a versão antiga) não tinha esse ficheiro, logo a comparação falha
e é criada uma cópia nova, **mesmo sem nenhum saldo alterado**. Isto acontece uma única vez; as cópias
seguintes sem alterações voltam a reutilizar a última.
Verificado: simulação com uma cópia sem `configuracao.csv` cria cópia nova; uma terceira exportação sem
alterações devolve a mesma pasta. **Por confirmar** com os ficheiros reais: que a cópia de 20/10 foi a
primeira depois do `git pull` desta versão, e se nesse dia também foi gravada a despesa mensal ou outro
valor (o que, por si só, também justificaria uma cópia nova).
