# Extensão — Adicionar um Novo Ativo

Se tens uma nova plataforma de investimento, mais um criptoativo, ou qualquer novo ativo que queiras rastrear, segue este guia.

## O que é um "Ativo"?

Um ativo é uma linha na tabela "Registo Mensal" que aparece uma vez por mês. Exemplos:

- Conta Principal (conta corrente)
- Investimentos: Degiro, Activobank, XTB, Trade Republic, etc.
- Numerário (dinheiro em casa)
- Criptoativos: Bitcoin, Ethereum, etc.

---

## Passo 1: Adiciona Linha em "Registo Mensal"

**Folha:** Registo Mensal

1. **Identifica onde colocar a nova linha**
   - Linhas 10-21 estão reservadas para os 12 ativos atuais
   - Se tens 12, a linha 22 é a primeira livre

2. **Clica em A22** (ou a primeira linha vazia)

3. **Preenche manualmente (ou copia de uma linha acima e edita):**
   - **Coluna A (Ano):** `=$B$3` (fórmula — copia de A10 acima)
   - **Coluna B (Mês):** `=$B$5` (fórmula — copia de B10 acima)
   - **Coluna C (MêsNum):** `=$B$4` (fórmula — copia de C10 acima)
   - **Coluna D (Categoria):** Escolhe entre:
     - `Investimento` (nova plataforma de investimento)
     - `Criptoativo` (novo crypto)
     - Deixa `Conta Principal` e `Numerário` como estão (só há um de cada)
   - **Coluna E (Ativo):** Nome do novo ativo (ex. "Ethereum", "Neon", etc.)
   - **Coluna F (Saldo):** deixa vazio (vai preencher mês a mês)
   - **Coluna G (Investido):** deixa vazio
   - **Coluna H (Ganho/Perda):** copia a fórmula de H10 acima e cole em H22

4. **Agora tens a estrutura pronta para "Registo Mensal"**

---

## Passo 2: Atualiza "Registo Mensal" para Incluir o Novo Ativo

Se antes copiavas **A10:H21** (12 ativos), agora copia **A10:H22** (13 ativos) a partir do próximo mês.

**Não precisas de refazer o histórico** — apenas a partir do próximo mês de entrada.

---

## Passo 3: Adiciona Linha em "Dados" (Histórico Futuro)

**Folha:** Dados

Quando chegares ao próximo mês mensal (passo 4 do workflow):

1. **Seleciona A10:H22** (incluindo agora a nova linha) em "Registo Mensal"
2. Copia e cola como valores em "Dados" (primeira linha vazia)
3. Estende o range da tabela "Dados" normalmente

---

## Passo 4: Verifica o Dashboard (Automático)

O **Dashboard** recalcula automaticamente — não precisas de fazer nada.

Se o novo ativo é um **Investimento**, aparecerá:
- Na tabela "Saldo por plataforma"
- Na tabela "Resumo por plataforma" (com saldo, investido, ganho/perda, % alocação)
- No gráfico de pizza de alocação

Se é um **Criptoativo**, aparecerá:
- Como um KPI separado em cima (tal como Bitcoin está agora)

---

## Exemplo: Adicionar "Ethereum"

Imagina que queres rastrear Ethereum além de Bitcoin.

### Em "Registo Mensal":

1. Copia a linha 21 (Bitcoin): A21:H21
2. Cola em A22
3. Muda E22 para "Ethereum"
4. Deixa F22, G22 vazios (vão preencher com dados reais)

### Próximo mês:

1. Preenche Saldo de Ethereum (F22) com o saldo real
2. Seleciona A10:H22 (agora 13 linhas)
3. Copia e cola em "Dados"
4. Estende o range de "Dados"

**Resultado:** Dashboard mostra um KPI de "Ethereum" ou inclui-o na tabela de Criptoativos.

---

## Exemplo: Adicionar Nova Plataforma de Investimento (ex. "Neon")

1. **Em "Registo Mensal":**
   - Coloca em linha 22 (ou a primeira livre)
   - D22: `Investimento`
   - E22: `Neon`
   - Copia fórmulas de A-C de uma linha acima

2. **Próximo mês:**
   - Preenche Saldo (F22) e Investido (G22) do Neon
   - Seleciona A10:H22, copia, cola em "Dados"

3. **Dashboard:**
   - Neon aparece em "Saldo por plataforma" (gráfico de linhas)
   - Neon aparece em "Resumo por plataforma" com % alocação

---

## Avisos

### ⚠️ Ordem das Linhas

As linhas 10-21 são fixas (12 ativos). Se adicionar um 13º ativo:
- Coloca em linha 22 (ou seguinte)
- **Não** reordenes as linhas 10-21, porque o Dashboard tem fórmulas que referem "Linha 10 = Activobank", etc.

### ⚠️ Nomes Únicos

Cada ativo deve ter um **nome único** em coluna E. Se tens dois "Degiro", as fórmulas de "Ganho/Perda" podem confundir-se.

### ⚠️ Categorias

Usa **exatamente** uma destas categorias (sensível a maiúsculas/minúsculas):
- `Conta Principal`
- `Investimento`
- `Numerário`
- `Criptoativo`

Se escreves `investimento` (minúscula), o Dashboard pode não reconhecer.

---

## Próximos Passos (Futura Melhoria)

No futuro, seria bom ter uma folha "Configuração" centralizada com:
- Dropdown de categorias
- Dropdown de ativos (validação)
- Isto reduziria erros de digitação

Por enquanto, faz manualmente seguindo este guia.

---

**Dúvidas?** Lê `workflow-mensal.md` para contexto de como os dados fluem.
