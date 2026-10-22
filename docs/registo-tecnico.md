# Registo técnico

Histórico das alterações relevantes ao código, uma entrada por commit (ou por sessão).
Serve para quem lê o repositório sem ter estado na sessão perceber o que mudou e porquê.
O que não foi verificado está marcado como "por confirmar".

Versão atual do esquema da base: **6** (`SCHEMA_VERSION` em `app/db.py`).

| Versão | Mudança | Migração |
|---|---|---|
| 1 | Tabelas `plataformas`, `registos_mensais`, `planos` | — |
| 2 | Coluna `registos_mensais.data_leitura` (AAAA-MM-DD, pode ser NULL) | `ALTER TABLE` em `_migrar` |
| 3 | Tabela `configuracao (chave TEXT PK, valor INTEGER)` | `CREATE TABLE IF NOT EXISTS` no arranque |
| 4 | Tabela `depositos_desafio (plataforma_id, domingo, valor_cent, mes)` | `CREATE TABLE IF NOT EXISTS` no arranque |
| 5 | Tabela `categorias (codigo PK, nome UNIQUE NOCASE, cor, ordem)`; `plataformas.categoria` passa de `CHECK` fixo a `REFERENCES categorias(codigo)` | Categorias de origem inseridas se a versão era < 5; tabela `plataformas` refeita em `_reconstruir_plataformas` (mesmos ids, transação, `foreign_keys` desligadas na troca e verificadas no fim) |
| 6 | Tabelas `indices (id, nome UNIQUE NOCASE, perimetro REFERENCES categorias NULL = património todo, ativo, ordem)` e `valores_indice (indice_id, mes, valor INTEGER > 0, em décimas de milésima)` | `CREATE TABLE IF NOT EXISTS` no arranque |

---

## Sessão 22/10/2026 — comparacao-com-indices-pwm
Commits `313445a` (esquema v6), `e51be38` (índices e check-in), `96bd809` (painel), `8fc1d7e` (ecrã estreito)
· 519 testes (+58; 461 antes)

**Pedido:** comparar o património com índices de referência (opção escolhida pelo dono: índices definidos por
ele, valor escrito à mão no check-in). A app continua offline: nada é descarregado.

**Decisões**
- **Rentabilidade ponderada no tempo** (sem contar com os aportes), porque a variação do saldo mistura dinheiro
  novo com rendimento. Por mês: `soma dos ganhos ÷ dinheiro em jogo no início do mês`, encadeado entre os dois
  meses com valor do índice (`dashboard._rentabilidades` e `_comparar`). Dinheiro em jogo: saldo anterior +
  aporte nas plataformas com ganho registadas no mês (os aportes fazem-se no início do mês); saldo anterior nas
  não registadas (rende 0 nesse mês; o ganho aparece todo quando voltam) e nas sem ganho (o dinheiro parado conta
  e rende 0). Os salários entram depois da leitura e não contam como dinheiro em jogo, por isso o aporte de um
  mês não é contado duas vezes (conta à ordem + plataforma).
- **Perímetro por índice:** uma categoria ou o património todo. Comparar um índice de ações com o património
  todo (PPR, certificados, contas à ordem) seria injusto; a inflação compara-se com o património todo.
- **Um índice é qualquer série:** nível de um índice, preço de um ETF de acumulação (já inclui dividendos e
  custos) ou índice de preços. Só as variações contam. A inflação sai com atraso: escreve-se o último valor
  publicado; o desfasamento é constante, as variações continuam comparáveis.
- **Valores como inteiros** em décimas de milésima (`indices.ESCALA = 10 000`), como o dinheiro em cêntimos. As
  variações calculam-se com `Fraction` (exatas) e só passam a `float` na apresentação.
- **Anualização só a partir de 12 meses**; com menos, a diferença é sobretudo ruído e o ecrã diz isso. Métricas
  ajustadas ao risco (volatilidade, Sharpe, tracking error) ficam de fora: com dados mensais precisam de 24 a 36
  meses para dizerem alguma coisa.
- **"Este ano"** começa no primeiro mês do ano com valor do índice, a mesma regra da variação do período.
- **Valores no check-in**, na mesma gravação tudo-ou-nada; em branco não mexe. Para corrigir, regrava-se o mês;
  apagar um valor faz-se em `/indices` (para um valor escrito no mês errado).
- Índice com valores não se apaga: desativa-se (sai do check-in e do painel, guarda o histórico).

**O que mudou**
- `app/db.py`: esquema v6 (tabelas novas, vazias numa base antiga). `app/backup.py`: `indices.csv` e
  `valores_indice.csv`. `app/restauro.py`: as duas tabelas são opcionais (cópias v5 restauram-se).
- `app/indices.py` (novo): validação dos valores, criar/editar/desativar/apagar, valores por mês.
- `app/calc.py`: `texto_para_decimal` separado de `euros_para_cent` (mesmas regras para euros e índices; a
  mensagem do valor ambíguo passa a dizer "casas decimais").
- `app/checkin.py`: `gravar_checkin(..., valores_indices=)`, `Resultado.erros_indices` e `indices_gravados`.
- `app/categorias.py`: uma categoria usada como perímetro de um índice não se apaga.
- `app/dashboard.py`: `ComparacaoPeriodo`, `Comparacao`, `Painel.comparacoes`, `_rentabilidades`, `_comparar`.
- `app/main.py`: rotas `/indices` (lista, criar, editar, desativar, reativar, apagar, apagar valor), campos
  `indice_<id>` no check-in, filtros Jinja `pct` e `pp`.
- Templates: `indices.html` (novo), secção no check-in, secção "Comparação com índices" no painel (ligada aos
  botões do período), link "Índices" na barra lateral. `pwm.css`: abaixo de 600 px o período passa para baixo
  do nome, para a diferença ficar à vista.
- `scripts/seed_demo.py`: dois índices fictícios com três valores.

**Testes:** `tests/test_indices.py` (32), `tests/test_main_indices.py` (7), `tests/test_comparacao.py` (13, contas
à mão em frações exatas: categoria, património todo, aportes não são rendimento, mês não registado, perímetro
sem dinheiro no início, "Este ano", anualização, formato), `tests/test_migracao.py` (+5, com o esquema exato da
v5 em `tests/esquema_v5.sql`), `tests/test_seed_demo.py` (+1).

**Verificado no Chromium** (cloud, `seed_demo`): valores no ecrã iguais aos de Python (+1,03 % vs +0,40 %,
+0,63 p.p.; +0,64 % vs +0,42 %, +0,22 p.p.); "Este ano" troca a tabela; índices pré-preenchidos no check-in; valor
inválido devolve o erro com o texto escrito; "Guardar e sair" pergunta com um valor de índice alterado e não
pergunta sem alterações ou com o valor reposto; sem erros de JavaScript; sem scroll horizontal a 420 e 1280 px
no painel, check-in e `/indices`. **Ensaio da migração:** base criada pelo código de `b12afdd` com o `seed_demo`,
aberta pelo novo: versão 5 → 6, dados das 6 tabelas iguais, `foreign_key_check` vazio, `integrity_check` ok.
**Por confirmar:** no Windows com a base real.

---

## Sessão 21/10/2026 — origem-crescimento-patrimonio-pwm
Commits `3cf2d33` (cálculo) e `f7db468` (ecrã) · 461 testes (+13; 448 antes)

**Pedido:** mostrar de onde vem o crescimento do património: quanto vem dos aportes e quanto do rendimento.

**Decisão de modelo:** "aportes + ganho" sozinho não explica a variação. Os aportes saem das contas à ordem
(plataformas sem ganho): são transferências internas, e o salário que fica na conta (ou a despesa que sai dela)
mexe no património sem ser aporte nem ganho. Por isso cada mês divide-se em quatro partes que **somam sempre a
variação do total, ao cêntimo** (`dashboard.Crescimento`):
- `aportes_cent`: aportes (e levantamentos) registados nas plataformas com ganho;
- `liquidez_cent`: variação do saldo das plataformas sem ganho (contas à ordem, numerário, cripto);
- `rendimento_cent`: soma dos ganhos do mês (pode ser negativo);
- `novas_cent`: saldo do primeiro registo de uma plataforma registada depois do primeiro mês (uma conta que já
  existia não passa por poupança).
No ecrã, aportes + liquidez chamam-se **"Dinheiro novo"** (o que ficou de lado dos salários). Não se usou
"Poupança" porque já é o nome de uma categoria.

**O que mudou**
- `app/dashboard.py`: `Crescimento`, `_crescimento` (usa os mesmos saldos do gráfico da evolução: uma plataforma
  não tocada num mês não muda, e o aporte e o ganho de vários meses aparecem no mês em que volta a ser
  registada), `Painel.crescimento` (um por mês, `None` no primeiro) e `dados_graficos()["crescimento"]`.
- `app/templates/dashboard.html`, `app/static/css/pwm.css`: secção "De onde veio o crescimento" por baixo da
  evolução, ligada aos mesmos botões "Este ano" / "Desde o início". Soma os meses depois do primeiro do período
  (a mesma regra da variação do período, por isso os números batem). Totais à esquerda (dinheiro novo com o
  detalhe aportes / contas sem ganho, rendimento, plataformas novas só se houver), barras empilhadas por mês à
  direita com a variação no rodapé da tooltip. Percentagens "% do crescimento" só quando todas as partes vão no
  mesmo sentido e o total é positivo (com rendimento negativo, uma parte passaria de 100 %). Com um só mês no
  período mostra uma frase em vez das partes. Fora dos formulários com `data-avisar-sair`.
- `README.md`: linha do painel.
- Sem mudança de esquema (versão 5).

**Testes:** `tests/test_crescimento.py` (13): separação das partes, dinheiro novo negativo, rendimento negativo,
levantamento, plataformas novas (com e sem ganho), mês não tocado, conta fechada, soma igual à variação em
dados aleatórios (8 plataformas, 22 meses), dados para o gráfico e página.

**Verificado no Chromium** (cloud, `seed_demo` + um mês 12-2025 fictício + uma plataforma nova em 09-2026):
valores no ecrã iguais aos de Python nos dois períodos (+2.669,24 €: dinheiro novo +957,00 €, rendimento
+1.212,24 €, plataformas novas +500,00 €); com rendimento negativo as percentagens desaparecem; base com um só
mês mostra a frase; "Guardar e sair" não pergunta depois de usar o filtro; sem erros de JavaScript; sem scroll
horizontal a 420 px e 1280 px. **Por confirmar:** no Windows com a base real (só tem 10-2026: deve aparecer a
frase do mês único até ao check-in de novembro).

**Limite conhecido:** um mês sem registo numa plataforma com ganho junta o aporte e o ganho de vários meses no
mês seguinte (a barra desse mês fica maior). É o mesmo comportamento do aviso "mês em falta" do ganho.

---

## Sessão 21/10/2026 — posicao-plataformas-por-lista-pwm
Commit `2c01bd2` · 448 testes (+23: 22 novos e +1 líquido nos ajustes; 425 antes)

**Pedido do dono:** escolher a "Ordem no ecrã" numa lista com a ordem atual, em vez de escrever um número.

**Decisão de desenho:** a lista "Posição" mostra só as plataformas **ativas da mesma categoria** ("No início da
categoria", "Depois de X", "No fim da categoria"), porque o painel agrupa por categoria. Mas a coluna `ordem`
continua **global**: o check-in e a tabela de `/plataformas` mostram uma lista única, e uma numeração por
categoria (1, 2, 3 em cada uma) intercalaria categorias diferentes no check-in. Por isso, ao gravar, a plataforma
é posta no sítio escolhido da ordem global e todas são renumeradas 10, 20, 30…, sem mudar a ordem relativa das
outras. As inativas ficam fora da lista (o check-in não as mostra).

**O que mudou** (`app/plataformas.py`, `app/main.py`, `app/templates/plataformas.html`)
- `Dados.ordem` (int) passa a `Dados.posicao` (texto): `""` (fim), `"inicio"` ou `"depois:<id>"`. Saíram
  `LIMITE_ORDEM` e `proxima_ordem`; o campo `ordem` do formulário é ignorado.
- `posicao_atual(conn, id)`: valor inicial no formulário de edição. `opcoes_posicao(conn)`: ativas pela ordem.
- `_posicionar` corre dentro da transação de `criar`/`atualizar`. Uma posição de outra categoria, inativa,
  inexistente ou a própria levanta `PosicaoInvalida` (subclasse de `ValueError`): nada é gravado e a rota
  mostra o erro no campo "Posição" (`_campo_do_erro` em `main.py`).
- Regras: gravar com a posição que já tinha não move a plataforma (mesmo que esteja intercalada com outra
  categoria); mudar de categoria põe-na no fim da nova; "início"/"fim" numa categoria sem outras ativas deixa-a
  onde estava (ou no fim de tudo, se for nova).
- Ecrã: um script esconde as opções de outras categorias e, se a escolhida deixar de servir ao mudar de
  categoria, volta a "No fim da categoria". Sem JavaScript, o servidor recusa.
- A primeira gravação depois do pull renumera a base real (10, 20, 30…) mantendo a ordem que se vê hoje; cria
  uma cópia de segurança nova, como qualquer gravação. Sem mudança de esquema.

**Testes:** `tests/test_posicao.py` (22: criar, editar, mudar de categoria, posições recusadas sem gravar nada,
inativas, check-in, ecrã) e ajustes ao campo antigo em `test_plataformas.py`, `test_main.py`, `test_aviso_sair.py`.

**Verificado no Chromium** (cloud, base do `seed_demo`, `/sair` intercetado): a editar "Corretora ETF B" a lista
mostra só "Depois de Corretora ETF A" e vem nela escolhida; sem alterações o "Guardar e sair" não pergunta; ao
mudar a categoria para Reforma aparecem só as duas PPR, a posição volta ao fim e o "Guardar e sair" pergunta;
"No início" gravado põe a ETF B antes da ETF A na tabela e no check-in; sem erros de JavaScript; sem scroll
horizontal a 420 px e 1280 px. **Por confirmar:** no Windows com a base real.

---

## Sessão 21/10/2026 — categorias-editaveis-pwm
Commits `07f14ca` (esquema) e `c27d067` (ecrã) · 425 testes (+38)

**Pedido:** poder acrescentar categorias (ex.: uma futura conta de rendimento de um side hustle). Escolhida a
opção A de três (A: lista editável numa tabela; B: texto livre com sugestões; C: acrescentar à lista fixa só
quando for preciso). Texto livre puro recusado: as categorias agrupam a alocação e a evolução e definem o fundo
de liberdade, e "Poupança"/"poupanca" passariam a ser duas categorias.

**Esquema v5** (`app/db.py`, `07f14ca`)
- Tabela `categorias`. O `codigo` é interno e nunca muda; o `nome` é o do ecrã. `db.CATEGORIAS_BASE` guarda as
  10 de origem (código, nome, cor); só são inseridas quando a versão da base era < 5, para uma categoria de
  origem apagada na app não voltar no arranque seguinte.
- `plataformas.categoria` liga-se a `categorias(codigo)` com `ON DELETE RESTRICT`. A migração reconhece a tabela
  antiga pela **falta** dessa ligação (não pela presença do `CHECK`, que as primeiras bases nem tinham) e refá-la.
  Se alguma plataforma tiver uma categoria fora da lista, aborta com `RuntimeError` e desfaz a troca.
- Backup: `categorias.csv` (primeiro em `backup.TABELAS`, por causa da ligação). Restauro: se a cópia tem o CSV,
  apagam-se as categorias de origem da base nova antes de carregar; cópias antigas sem ele ficam com as de origem
  (as únicas que existiam até à v4). **A primeira cópia depois do pull cria uma pasta nova** (passa a ter
  `categorias.csv`), uma vez, como na v3 e na v4.
- Testes: `tests/test_migracao.py` (+6) com o esquema exato da v4 em `tests/esquema_v4.sql`.

**Categorias no ecrã** (`app/categorias.py` novo, `main.py`, `plataformas.html`, `dashboard.py`, `checkin.py`)
- Secção "Categorias" no fim de `/plataformas`: renomear e apagar em cada linha, e criar uma nova. Rotas
  `POST /categorias`, `POST /categorias/{codigo}` e `POST /categorias/{codigo}/apagar`, com backup depois de cada.
- Regras: nome sem espaços a mais, até 40 caracteres; repetidos recusados comparando sem maiúsculas, acentos nem
  símbolos; código novo tirado do nome (com sufixo `_2` se estiver ocupado); cor nova da lista `CORES_NOVAS`
  (a primeira livre); fica no fim da ordem. Só se apaga sem plataformas (inativas incluídas); `emergencia` nunca.
- O painel, o check-in e o formulário de plataformas leem nomes, cores e ordem da base: saíram
  `dashboard.ROTULOS_CATEGORIA`, o filtro Jinja `categoria` e as cores fixas do `dashboard.html`.
- `plataformas.validar(form, categorias_validas)`: a web passa os códigos da base; sem eles valem os de origem.
- Os formulários das categorias entram no aviso do "Guardar e sair" (`data-avisar-sair`). A página desce para a
  secção depois de criar, renomear ou apagar, e com erro.
- Limite conhecido: criar uma categoria a meio de editar uma plataforma recarrega a página e perde o que estava
  escrito nessa plataforma (o ecrã diz para gravar primeiro). Não há forma de mudar a ordem nem a cor no ecrã.

**Verificado:** base criada pelo código da v4 (`ecfd01b`) com o `seed_demo`, aberta pelo código novo: versão 5,
dados das 5 tabelas iguais, `foreign_key_check` vazio, `integrity_check` ok; painel, check-in e plataformas sem
erro; categoria criada, atribuída a uma plataforma e visível no painel (com a cor nova) e no check-in.
**Por confirmar no ecrã:** o aspeto da secção "Categorias" (sem Chromium na cloud nesta sessão).

---

## Sessão 21/10/2026 — editar-plataforma-salta-formulario-pwm
387 testes (+3)

**Problema relatado:** em `/plataformas`, carregar em "Editar" parecia não fazer nada. Na verdade o endereço
mudava para `/plataformas/<id>` e o formulário de edição abria, mas fica **por baixo da tabela**: com 12
plataformas está fora do ecrã e a página não se mexia. O servidor estava certo (verificado: as 11
plataformas da demo abertas em edição e gravadas sem alterações deixam a base igual).

**O que mudou** (`app/templates/plataformas.html`, `app/static/css/pwm.css`)
- O link "Editar" passa a `/plataformas/<id>#formulario` e o título do formulário tem `id="formulario"`:
  o browser salta logo para lá, sem JavaScript.
- A linha da plataforma em edição fica destacada na tabela (classe `a-editar`).
- Ecrã devolvido com erro num campo (o endereço do POST não leva âncora): um script curto faz
  `scrollIntoView` do formulário, para o erro não ficar escondido.
- Sem mudança de esquema.

**Testes:** `tests/test_plataformas.py` (âncora no link, linha destacada só na plataforma em edição,
salto no ecrã com erro). Os testes não executam JavaScript: o salto no browser está **por confirmar** no ecrã
(nesta sessão não havia Chromium na cloud).

---

## Sessão 21/10/2026 — grafico-evolucao-linha-filtro-pwm
Commit `edf0f1f` · 384 testes (+4)

**Pedido:** gráfico da evolução em linha, com filtro "este ano" / "desde o início". Escolhido o meio-termo:
linha do total com categorias opcionais e dois períodos, sem zoom nem intervalos à medida.

**O que mudou**
- O gráfico de barras empilhadas por categoria passa a **linha**. O património total é a linha principal
  (com área preenchida); cada categoria é uma linha fina, **escondida por defeito**, que se liga clicando
  na legenda. Tooltip mostra todos os valores visíveis do mês.
- Botões **"Este ano"** e **"Desde o início"** (padrão: desde o início). O filtro corre no browser, sem novo
  pedido ao servidor: os dados de todos os meses já vêm na página.
- Por cima do gráfico: variação do período (primeiro → último mês visível) em euros e percentagem. Com um só
  mês no período, explica que a variação aparece a partir do segundo.
- `dashboard.dados_graficos` envia `total_cent` (soma das categorias por mês, cêntimos inteiros) e
  `inicio_ano` (posição do primeiro mês do ano do **último mês com registos**, não do dia de hoje).

**Ficheiros:** `app/dashboard.py`, `app/templates/dashboard.html`, `app/static/css/pwm.css`, `README.md`;
testes em `test_dashboard.py`.

**Decisões**
- "Este ano" começa em janeiro do ano do painel, sem dezembro do ano anterior como ponto de partida: a variação
  mede-se de janeiro ao último mês. Se se quiser o valor de fecho do ano anterior como base, é mudar `inicio_ano`
  para uma posição antes.
- A variação inclui aportes (é variação do património, não rendimento). O ganho continua no cartão do mês.
- Os botões do filtro estão fora dos formulários com `data-avisar-sair`: mudar de período não dispara o aviso.

**Verificado:** 384 testes; Chromium na cloud com base fictícia (`seed_demo` + 11 meses anteriores inventados,
08-2025 a 09-2026): tipo linha, 14 meses em "Desde o início", 9 em "Este ano", botões trocam `aria-pressed`,
variações iguais às calculadas em Python (+4.895,89 € / +24,7 %; +3.117,64 € / +14,4 %), categoria ligada
mantém-se ao mudar de período, "Guardar e sair" sem pergunta depois de usar o filtro, sem erros de JavaScript,
layout a 420 px de largura. **Por confirmar:** no Windows com a base real (só tem 10-2026: um ponto e a frase
do mês único).

**Esquema:** sem alterações (versão 4).

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
