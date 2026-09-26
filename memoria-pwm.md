# Personal Wealth Manager — Memória do Projeto

> Este ficheiro é o "estado atual" do projeto. Não é um diário de sessões — reflete sempre a situação mais recente. É partilhado no menu Contexto deste projeto, juntamente com o `.xlsx` atualizado. No início de cada sessão nova, ler este ficheiro primeiro.

## Acesso ao computador do utilizador

Claude tem acesso (via extensão Filesystem/Filesync) ao diretório local:
`C:\Users\User\Projetos\Personal Wealth Manager`
Pode ler e escrever ficheiros diretamente aí (incluindo este `.md` e o `.xlsx`), sem precisar que o utilizador faça upload manual — **mas só quando essa integração está disponível na sessão** (ex. Claude Desktop/Cowork). Em sessões de chat sem essa integração (ex. claude.ai web), Claude não tem esse acesso direto e trabalha a partir de upload/download manual — como aconteceu na sessão de 01/09/2026, em que o utilizador teve de fazer upload do `.xlsx` e descarregar o corrigido manualmente. Diretórios permitidos quando a integração está ativa, em geral: `C:\Users\User\Documents`, `C:\Users\User\Pictures`, `C:\Users\User\Projetos`.

## Objetivo do projeto

Reestruturar o registo de finanças pessoais (`Portefólio.xlsx` original) para ser mais fácil de ler e de analisar, mantendo-o no LibreOffice Calc. O ficheiro de trabalho atual chama-se **`Personal Wealth Manager.xlsx`** e está nesta mesma pasta.

## O que o utilizador quer tirar da análise (não mudar sem confirmar)

- Quanto tem na Conta Principal (conta do dia a dia) e qual a média do saldo com que começa cada mês.
- Quanto investiu em cada plataforma de investimento e ver a evolução/progresso de cada uma.
- Percentagem de alocação entre as diferentes plataformas de investimento.
- Numerário (dinheiro em casa) e Criptoativos (acumulados via faucets/airdrops) são acompanhados à parte — **não** entram no cálculo de alocação % dos investimentos, porque não são "investimentos" no mesmo sentido.

## Decisões estruturais tomadas

1. **Formato longo, não largo.** Trocámos o layout antigo (uma folha por ano, 3 colunas por mês × 12 meses) por uma tabela longa (`Ano | Mês | Categoria | Ativo | Saldo | Investido | Ganho/Perda`), muito mais fácil de somar/filtrar/graficar.
2. **Só a partir de 2026 para a frente é gerido na estrutura nova.** As folhas `2023`, `2024`, `2025` ficam como **arquivo histórico**, sem alteração de estrutura — só lá se corrigiu um problema técnico que impedia o ficheiro de abrir sem erros (ver secção de correções).
3. **Categorias fixas:**
   - `Conta Principal` — só Saldo (sem Investido/Ganho-Perda). Um único ativo: "Conta Principal".
   - `Investimento` — Saldo + Investido + Ganho/Perda (calculado). Ativos atuais: Activobank, Bondora Go & Grow, Degiro, Golden SGF, IGCP, PPR Santander, Revolut, Trade Republic, XTB.
   - `Numerário` — só Saldo. Ativo: "Numerário (dinheiro em casa)". Antiga categoria "Extra" foi renomeada e passou a ser independente dos Investimentos.
   - `Criptoativo` — só Saldo. Ativo atual: Bitcoin. (Vem de faucets/airdrops, não é "investido" dinheiro próprio.)
4. Se um dia se quiser adicionar um novo ativo (ex. nova plataforma de investimento, ou mais um criptoativo), é preciso acrescentar a linha correspondente **tanto** na folha `Registo Mensal` como na lógica de migração/lista de ativos — avisar para eu ajustar as fórmulas de resumo no Dashboard também. (Nota: ainda não existe uma folha "Configuração" centralizada para isto — ficou identificado como melhoria possível, ver "Em aberto".)

## Estrutura do ficheiro `.xlsx`

Ordem das folhas: **Dashboard → Registo Mensal → Dados → 2026 (formato antigo) → 2025 → 2024 → 2023**

### Folha "Dados"
Tabela Excel (`TabDados`, atualmente `A1:H85`, cresce para baixo — **o range da tabela tem de ser estendido manualmente sempre que se adicionam linhas**, ver correção técnica nº 7). Colunas:
`Ano | Mês | MêsNum | Categoria | Ativo | Saldo | Investido | Ganho/Perda`

- `Ganho/Perda` só é calculado para linhas `Categoria = "Investimento"`. Usa uma chave `Ano*100+MêsNum` com `SUMPRODUCT(MAX(...))` para encontrar, para o mesmo Ativo, o registo cronologicamente mais recente **anterior** ao atual (chave estritamente menor). Fórmula: Saldo atual − Saldo desse registo anterior − Investido do mês atual. Se não existir registo anterior (primeiro mês em que o ativo aparece), fica em branco. Sem colunas auxiliares — tudo inline.
- O intervalo usado nas fórmulas (`$A$2:$A$1000` etc.) vai até à linha 1000 — margem para ~80 meses de dados sem precisar de ajustar fórmulas.
- **Dados migrados/registados até à data:** Janeiro a Maio de 2026 (formato largo original) + Julho de 2026 + **Agosto de 2026** (ambos registados diretamente na estrutura nova).
- **Junho de 2026 foi deliberadamente saltado** ("interregno assumido"). Não existe linha com `MêsNum = 6`. A fórmula de `Ganho/Perda` tolera isto sem deixar valores em branco a mais.

### Folha "Registo Mensal"
Onde se preenche um mês de cada vez.
- `B3` = Ano (input), `B4` = nº do mês 1-12 (input), `B5` = nome do mês (fórmula `INDEX`).
- 12 linhas fixas (uma por Ativo). **Desde 01/09/2026, as colunas Ano/Mês/MêsNum (A10:C21) são fórmulas** (`=$B$3`, `=$B$5`, `=$B$4`) — deixaram de ser texto fixo (ver correção técnica nº 7). Células de **Saldo** e **Investido** continuam a ser inputs manuais. `Ganho/Perda` calcula-se sozinho, comparando com o registo anterior mais recente em "Dados".
- **Workflow mensal correto (revisto):**
  1. Muda `B4` para o número do mês a introduzir. `B5` e agora também A10:C21 atualizam-se sozinhos.
  2. Preenche Saldo (e Investido, só nas linhas de Investimento) de cada ativo.
  3. Confere Ganho/Perda (H10:H21).
  4. Seleciona **A10:H21** (⚠️ SEM a linha 9 do cabeçalho — ver correção técnica nº 7) e copia.
  5. Cola **como valores** (Ctrl+Shift+V no LibreOffice, "Colar apenas valores") na primeira linha livre da tabela "Dados".
  6. **Estende o range da tabela `TabDados`** (Dados → clicar dentro da tabela → arrastar o canto ou Formatar > Definir Intervalo de Base de Dados) para incluir as novas linhas.
  7. Só depois disso muda `B4` para o mês seguinte, e limpa Saldo/Investido das 12 linhas para a próxima entrada.
- A nota de instruções na célula A7 desta folha foi corrigida para refletir o intervalo certo (A10:H21).

### Folha "Dashboard"
- `B3` = Ano corrente (input). `B4` = mês mais recente com dados (fórmula `_xlfn.MAXIFS` — nunca escrever à mão).
- KPIs: saldo/média da Conta Principal, saldo de Numerário, saldo de Criptoativos (linhas 6-8).
- Tabela "Evolução mensal" (património total + por categoria, linha 12-24) + gráfico de linhas.
- Tabela "Saldo por plataforma de investimento" (linha 27-37) + gráfico de linhas.
- Tabela "Resumo por plataforma" — saldo atual, investido acumulado, ganho/perda acumulado, alocação % (linha 40-51) + gráfico de pizza da alocação.
- Tabela "Histórico anual" (linha 55-59) + gráfico de barras — três valores fixos para 2023/2024/2025, fonte documentada em comentário (ver ficheiro original para os valores).
- **Coluna A congelada (`freeze_panes = B1`), desde 01/09/2026.** Ao arrastar a folha para a direita nas tabelas "Saldo por plataforma" e "Resumo por plataforma" (que crescem para a direita, mês a mês), a coluna com os nomes das plataformas fica sempre visível. Não foi congelada nenhuma linha — só fazia falta a coluna.

## Correções técnicas feitas (para não repetir)

1. **Bug de fórmula:** Total de Janeiro/2026 excluía a XTB. Resolvido com `SUMIFS`.
2. **Fórmulas `Minus()`** (Google Sheets) existentes nas folhas 2026 e 2025 (120 células). Substituídas por subtração direta.
3. Ficheiro validado com `recalc.py` antes de ser entregue — repetir sempre após alterações estruturais.
4. **(01/08/2026) Desalinhamento Julho/Junho no Dashboard**, por `MêsNum` errado colado. Corrigido; `Dashboard!B4` reposto como fórmula `MAXIFS`.
5. **(01/08/2026) Redesenho da fórmula de `Ganho/Perda`** para chave `Ano*100+MêsNum` com `SUMPRODUCT(MAX(...))`, tolerando lacunas de qualquer tamanho.
6. Confirmar sempre se o LibreOffice está aberto (processo, não só o ficheiro `.~lock.*#`) antes de editar o `.xlsx` diretamente em disco.
7. **(01/09/2026) Incidente ao introduzir Agosto/2026 — duas causas em simultâneo, ambas corrigidas:**
   - **(a) Intervalo de cópia mal definido.** A instrução original (tanto minha como o texto da célula A7 do Registo Mensal) dizia "seleciona A9:H20", o que é matematicamente inconsistente: esse intervalo cobre só 12 linhas ao todo (cabeçalho da linha 9 + 11 ativos), excluindo o Bitcoin (linha 21). O utilizador, corretamente, selecionou o suficiente para apanhar os 12 ativos — o que incluiu a linha 9 (cabeçalho) por engano. Esse texto ("Ano", "Mês"...) foi colado como linha de dados na "Dados" e, por estar numa coluna que as fórmulas tratam como numérica (`$A$2:$A$1000*100`), partiu o cálculo de `Ganho/Perda` em toda a tabela (`#VALOR!` em cascata). **Corrigido**: intervalo certo é **A10:H21** (só dados, sem cabeçalho) — já atualizado na célula A7 e neste ficheiro.
   - **(b) Ano/Mês/MêsNum eram texto fixo, não fórmula, no Registo Mensal.** A10:C21 tinham "2026"/"Julho"/"7" escritos à mão em cada linha, sem ligação a B3/B4/B5. Ao mudar `B4` para 8, só `B5` (o texto no topo) se atualizou sozinho — a mini-tabela por baixo, de onde se copia, continuou presa em Julho. Resultado: os saldos de Agosto foram colados na "Dados" etiquetados como uma segunda entrada de Julho, duplicando a chave `Ano+MêsNum` e fazendo os `SUMIFS` do Dashboard somarem as duas entradas de Julho (ex. Conta Principal a aparecer como €5.346,78 = €3.377,66 + €1.969,12). **Corrigido estruturalmente**: A10:C21 passaram a fórmulas `=$B$3` / `=$B$5` / `=$B$4` — este tipo de bug já não se pode repetir, porque a mini-tabela segue sempre o mês definido em B3/B4.
   - Ao corrigir, também se reconstruiu a fórmula de `Ganho/Perda` das 12 linhas de Agosto (estava congelada com um valor errado, calculado contra Maio em vez de Julho, por causa da duplicação) e estendeu-se o range da tabela `TabDados`, que estava parado em `A1:H61` desde antes de Julho ser introduzido (não afetava os cálculos, que usam ranges diretos, mas afetava filtros/formatação da tabela).
   - Ficheiro revalidado: 0 erros em 609 fórmulas. Números confirmados sem duplicação (Julho €39.808,01 / Agosto €38.970,51 na Evolução mensal, valores distintos).

## Notas soltas

- O aviso "Non-standard file format" ao gravar no LibreOffice é normal — escolher sempre "Use Excel 2010-365 Spreadsheet Format" para manter `.xlsx`.
- O utilizador ajustou manualmente larguras de coluna após a entrega — o ficheiro em `C:\Users\User\Projetos\Personal Wealth Manager\Personal Wealth Manager.xlsx` é a versão de referência (quando a integração Filesystem está ativa) ou o último `.xlsx` descarregado do chat (quando não está).

## Em aberto / possíveis próximos passos

- **Folha "Configuração" com lista centralizada de ativos/categorias**, ligada por validação de dados a "Registo Mensal" — reduziria o risco de erro de digitação e centralizaria a manutenção quando se adiciona uma plataforma nova. Ainda não implementada (~30 min de esforço estimado).
- **Comentário de definição na fórmula `Ganho/Perda`** documentando exatamente o que representa (variação de saldo não explicada por aportes registados) — útil sobretudo se um dia se começar a registar dividendos/juros separadamente.
- Confirmar se os Criptoativos devem entrar (com valor aproximado) nos pontos históricos de 2024/2025, atualmente excluídos por falta de dado de fecho fiável.
- Validar com o utilizador o resultado visual dos gráficos no Dashboard (cores, disposição) — ainda sem feedback.
- **Lembrete de processo**: sempre que se propuser um passo manual ao utilizador que envolva selecionar um intervalo de células, confirmar a matemática do intervalo antes de o escrever (o erro da correção nº 7a foi exatamente isto — instrução verbal inconsistente com a referência de células dada).
