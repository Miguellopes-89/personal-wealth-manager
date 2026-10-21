# Registo técnico

Histórico das alterações relevantes ao código, uma entrada por commit (ou por sessão).
Serve para quem lê o repositório sem ter estado na sessão perceber o que mudou e porquê.
O que não foi verificado está marcado como "por confirmar".

Versão atual do esquema da base: **4** (`SCHEMA_VERSION` em `app/db.py`).

| Versão | Mudança | Migração |
|---|---|---|
| 1 | Tabelas `plataformas`, `registos_mensais`, `planos` | — |
| 2 | Coluna `registos_mensais.data_leitura` (AAAA-MM-DD, pode ser NULL) | `ALTER TABLE` em `_migrar` |
| 3 | Tabela `configuracao (chave TEXT PK, valor INTEGER)` | `CREATE TABLE IF NOT EXISTS` no arranque |
| 4 | Tabela `depositos_desafio (plataforma_id, domingo, valor_cent, mes)` | `CREATE TABLE IF NOT EXISTS` no arranque |

---

## Sessão 21/10/2026 — aviso-sair-painel-plataformas-pwm
Commit `a5eafd0` · 380 testes (+12)

**Problema que motivou a mudança:** "Guardar e sair" faz a cópia de segurança e fecha a aplicação, mas não
grava formulários. Só o check-in avisava; a despesa mensal do painel e o formulário de plataformas perdiam
o que estava escrito sem aviso.

**O que mudou**
- Um só script em `base.html` (a seguir à barra lateral) trata do aviso em todos os ecrãs. Verifica os
  formulários marcados com `data-avisar-sair`: check-in, despesa mensal do painel e formulário de plataforma
  (criar e editar).
- Cada campo compara-se com o valor que o servidor escreveu na página (`defaultValue`, `defaultChecked`,
  e para listas a opção marcada por defeito, ou a primeira se nenhuma estiver). Escrever e repor o valor
  original não avisa. Campos escondidos e botões não contam.
- Um ecrã devolvido com erro (422) leva `data-por-gravar` no formulário e avisa sempre: os valores no ecrã
  foram escritos mas nunca gravados. No check-in, `_contexto` passa `por_gravar` quando há erros por linha.
  Antes, o check-in devolvido com erro não avisava.
- O script próprio do check-in para o aviso saiu (com os dois ativos haveria duas confirmações seguidas).
  O script das caixas do Desafio fica igual.

**Ficheiros:** `app/templates/base.html`, `app/templates/checkin.html`, `app/templates/dashboard.html`,
`app/templates/plataformas.html`, `app/main.py`; testes em `test_aviso_sair.py` (novo).

**Decisões**
- Marcar formulários com um atributo em vez de vigiar todos: o formulário "Abrir" do check-in (GET, mês e data)
  e os botões desativar/reativar/apagar não gravam valores escritos, logo não devem avisar.
- Comparar com os valores por defeito do HTML em vez de guardar uma cópia ao carregar a página: dá o mesmo
  resultado e funciona para qualquer formulário marcado, sem código por ecrã.
- Fora do âmbito: sair da página pelos links da barra lateral (Painel, Check-in, Plataformas) continua a
  perder valores sem aviso. Resolve-se com `beforeunload`, que tem de ser desligado no envio do próprio
  formulário; fica como ideia.

**Verificado:** 380 testes. No Chromium (cloud, base do `seed_demo`), com `/sair` intercetado: 15 casos certos
— sem alterações sai sem perguntar; despesa escrita, nome escrito, categoria mudada, caixa "entra na alocação"
mudada, saldo escrito e caixa do Desafio desmarcada perguntam e ficam na página; despesa escrita e reposta,
nova plataforma intacta (lista em "—") e só a data do topo do check-in mudada não perguntam; os três ecrãs
devolvidos com erro perguntam.
**Por confirmar:** no Windows, com a base real.

**Esquema:** sem alterações (versão 4).

---

## Sessão 21/10/2026 — registo-depositos-desafio-pwm
Commits `9a6ce74`, `a851296`, `c51319d` · 368 testes (+44)

**Problema que motivou a mudança:** a sugestão do aporte da Bondora somava os domingos entre a leitura anterior
e a atual. Um depósito que ainda não estivesse no saldo no dia da leitura (ex.: domingo 1/11 com leitura a 1/11)
e fosse retirado do aporte nunca mais era sugerido: a leitura seguinte começava depois desse domingo, e quando
o dinheiro entrasse contava como **ganho**. O painel também só mostrava o plano, não o que foi depositado.

**O que mudou**
- `9a6ce74` — esquema v4: tabela `depositos_desafio` (um domingo confirmado por plataforma, com o valor e o mês
  do check-in em que entrou). `domingo` tem de ser uma data válida e um domingo; FK composta para
  `registos_mensais(plataforma_id, mes)`. Entra em `backup.TABELAS` e em `restauro.TABELAS_OPCIONAIS`.
- `a851296` — check-in: uma caixa por domingo em aberto (marcadas por defeito; num mês já gravado, marcadas só
  as confirmadas). Marcar/desmarcar soma/tira o valor ao aporte (JavaScript; o aporte continua editável).
  Os marcados ficam em `depositos_desafio`; regravar o mês substitui-os. Um desmarcado volta no check-in
  seguinte com "em atraso". Aviso depois de gravar se o aporte não bater com a soma das caixas.
  "Guardar e sair" também avisa com caixas alteradas. Demo (`seed_demo`) com os depósitos confirmados.
- `c51319d` — painel: o previsto do ano até hoje divide-se em anteriores ao registo, confirmados, em falta
  (com semana e data) e por confirmar no próximo check-in; as quatro partes somam sempre o previsto.

**Ficheiros:** `app/db.py`, `app/backup.py`, `app/restauro.py`, `app/planos.py` (`Semana.em_atraso`,
`sugerir_desafio(excluir=, atraso_ate=)`), `app/checkin.py` (`domingos_em_aberto`, `confirmados`,
`_gravar_depositos`, `Entrada.domingos`, `Linha.domingos_marcados`), `app/main.py`, `app/dashboard.py`,
`app/templates/checkin.html`, `app/templates/dashboard.html`, `app/static/css/pwm.css`, `scripts/seed_demo.py`,
`README.md`; testes em `test_depositos_desafio.py` (novo), `test_migracao.py`, `test_restauro.py`,
`test_checkin_plano.py`, `test_main_plano.py`, `test_dashboard.py`, `test_seed_demo.py`.

**Decisões**
- Domingos em aberto = domingos do plano **depois da primeira leitura datada** da plataforma e até à leitura
  atual, menos os confirmados noutros meses. Os anteriores à primeira leitura estão no saldo inicial: não se
  pedem nem se dão como verificados ("anteriores ao registo" no painel).
- O formulário manda um campo escondido `desafio_<id>` quando a linha tem caixas (as desmarcadas não vão no
  POST). Sem esse campo (`Entrada.domingos = None`, ex.: chamadas antigas), todos os domingos em aberto contam
  como confirmados, que era o significado do aporte sugerido antes da v4.
- A validação das caixas corre dentro da transação e usa a data da leitura **efetivamente gravada** (uma linha
  regravada igual mantém a sua data); uma caixa inválida desfaz a gravação toda.
- O valor de cada depósito é sempre o do plano (n €); um depósito diferente do plano vai no aporte e gera o
  aviso de diferença.
- Limitação conhecida: uma base com vários meses gravados **antes** da v4 mostraria os domingos desses meses
  como "em atraso" (não há confirmações). A base real só tinha o saldo inicial de outubro: não se aplica.
  Também: um mês gravado com todas as caixas desmarcadas reabre com todas marcadas (sem confirmações não se
  distingue de um mês anterior à v4); o aviso de diferença no aporte apanha uma regravação por engano.
- Efeito no backup: a primeira cópia depois do `git pull` cria uma pasta nova (passa a ter
  `depositos_desafio.csv`), tal como aconteceu com o `configuracao.csv` a 20/10.

**Verificado:** 368 testes; no Chromium (Playwright, base fictícia na cloud): desmarcar/marcar acerta o
aporte, gravação, partes do painel (703 + 117 + 41 + 42 = 903 € = semanas 1 a 42), e o aviso do
"Guardar e sair" no check-in (sem alterações sai; com caixa desmarcada ou saldo escrito pergunta e fica).
**Por confirmar:** o ecrã no Windows com a base real depois do `git pull` (migração v3 → v4 no arranque).

**Esquema:** **subiu de 3 para 4.** Migração: `CREATE TABLE IF NOT EXISTS` no arranque (`init_db`); bases v3
abrem sem perder dados. Testado em `test_migracao.py`.

---

## Sessão 21/10/2026 — novo-modelo-de-trabalho-pwm
324 testes (sem alterações ao código)

**O que mudou:** o modelo de trabalho. O Claude Code passa a ser o responsável principal pela arquitetura
e pela programação; desenvolve num clone na cloud e faz push para `main`. A app passa a correr com os dados
reais num computador Windows novo, cuja pasta do projeto é um clone Git que só recebe `git pull --ff-only`.
O computador antigo (pasta no OneDrive) deixa de fazer parte do fluxo depois da migração dos dados.

**Ficheiros:** `CLAUDE.md` (secção "Modelo de trabalho"; início e fim da sessão ajustados).

**Decisões:**
- O `estado-projeto.md` continua fora do Git (dados pessoais), mas passa a viver na pasta do projeto do
  computador do dono; o Claude lê-o e atualiza-o pela ligação ao computador, em vez de copiar e colar.
- A recusa de bases no OneDrive mantém-se: não custa nada e protege contra corrupção por sincronização.
- Migração dos dados: copiar a pasta de cópia de segurança mais recente para `backup\` do novo clone e
  correr `python -m app.restauro --destino "%LOCALAPPDATA%\pwm\pwm.db"` (o restauro nunca sobrescreve,
  por isso só funciona enquanto essa base não existir).

**Verificado no computador novo (21/10/2026):** clone Git em `%USERPROFILE%\Projetos\personal-wealth-manager`,
venv em `%LOCALAPPDATA%\pwm\venv` com Python 3.14.8, 324 testes a passar; restauro da cópia mais recente
(12 plataformas, 11 registos, 1 plano, configuração vazia); `pwm.bat` arranca, serve o painel e os ficheiros
locais, e "Guardar e sair" fecha a app. Pedido a `/favicon.ico` dá 404 (sem impacto).

**Esquema:** sem alterações (versão 3).

---

## Sessão 21/10/2026 — registo-tecnico-retroativo-e-claude-md
Commits `a9b43c9` e `792ed71` · 324 testes (sem alterações ao código)

**O que mudou:** criados `CLAUDE.md` (regras permanentes das sessões, sem dados pessoais) e este
`docs/registo-tecnico.md`, preenchido a partir do código e do histórico Git para os commits 8a4a9dc a 0e71688.

**Ficheiros:** `CLAUDE.md` (novo), `docs/registo-tecnico.md` (novo).

**Decisões:** o registo fica no repositório para a conta que acompanha o projeto o poder ler via GitHub.
A explicação da cópia de 20/10 foi verificada por simulação, não com os ficheiros reais.

**Esquema:** sem alterações (versão 3).

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
alterações devolve a mesma pasta. Bate com o histórico do projeto: até 20/10 o backup devolvia sempre a
cópia de 15/10; a 20/10 o código foi atualizado para `0e71688` (esquema v3) e a despesa mensal ainda não
estava definida. **Por confirmar** com os ficheiros reais: a cópia de 20/10 deve ter um `configuracao.csv`
só com o cabeçalho e os outros três CSV iguais aos da cópia de 15/10. Se algum CSV diferir, houve também
uma alteração de dados nesse período.
