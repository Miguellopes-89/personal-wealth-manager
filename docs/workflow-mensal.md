# Workflow Mensal — Passo a Passo

Este documento descreve o ciclo mensal de utilização do Personal Wealth Manager, após o setup inicial (ver `setup.md`).

## Ciclo Mensal em 5 Passos

### 1. Prepara "Registo Mensal" para o Novo Mês

**Folha:** Registo Mensal

- Célula `B4` (Mês): muda para o número do mês (1-12)
  - Exemplos: `1` (Janeiro), `2` (Fevereiro), ..., `12` (Dezembro)
- Célula `B5` (Nome do mês) atualiza-se automaticamente
- As células A10:C21 (Ano | Mês | MêsNum) também atualizam-se — **não precisas de tocar nelas**

Agora a mini-tabela (linhas 10-21) está pronta para o novo mês.

### 2. Preenche Saldos

Para cada ativo (linha 10-21):

- **Coluna F (Saldo):** escreve o saldo atual do ativo (obrigatório para todos)
- **Coluna G (Investido):** 
  - Se é um **Investimento** (ex. Degiro, Activobank): escreve quanto foi investido **este mês** (novo dinheiro introduzido)
  - Se é **Conta Principal**, **Numerário** ou **Bitcoin**: deixa em branco
- **Coluna H (Ganho/Perda):** deixa em branco — calcula-se automaticamente

**Dica:** Se não houve novo investimento este mês, deixa G vazio (ou escreve 0).

### 3. Verifica Ganho/Perda (Opção)

Coluna H mostra automaticamente quanto ganhou ou perdeu cada investimento:

```
Ganho/Perda = Saldo Atual − Saldo Anterior − Investido Este Mês
```

**Exemplos:**
- Saldo anterior: €1000, Saldo atual: €1100, Investido este mês: €0 → Ganho/Perda: +€100 ✓
- Saldo anterior: €1000, Saldo atual: €1150, Investido este mês: €100 → Ganho/Perda: +€50 ✓
- Primeiro mês com este ativo → Ganho/Perda: (vazio) — é normal, sem comparação anterior

Se parecer errado, volta a "Dados" e verifica o registo anterior desse ativo.

### 4. Copia para "Dados"

Quando acabaste de preencher todas as linhas de um mês:

1. **Seleciona o intervalo A10:H21** (as 12 linhas de ativos, **sem a linha 9 do cabeçalho**)
   - Clica em A10, depois Shift+Click em H21
   - Ou: A10, depois Shift+Ctrl+End (se H21 for a última célula com conteúdo naquela secção)

2. **Copia:** Ctrl+C

3. **Vai para "Dados"**

4. **Clica na primeira linha vazia** (após o último registo)
   - Se é o primeiro mês (Janeiro), é A2
   - Se já tens Julho, é A14 (porque Julho são 12 linhas, então A2+12 = A14)

5. **Cola como valores:** Ctrl+Shift+V
   - Diálogo "Colar Conteúdo"
   - Desmarcar tudo, deixar **apenas "Números"** marcado
   - OK

   (Isto garante que copias só os valores, não as fórmulas de A10:C21 — que já estão corretas para o mês.)

### 5. Estende o Range da Tabela "Dados"

1. **Clica dentro da tabela "Dados"** (qualquer célula do intervalo A1:H`X`)

2. **Formatar → Definir Intervalo de Base de Dados** (ou clica direito na tabela)

3. **Novo intervalo:** Dados.$A$1:$H$`Y`
   - Onde Y = número de linhas que tens agora
   - Exemplo: Se acabas de adicionar Fevereiro (12 linhas de Janeiro + 12 de Fevereiro), Y = 25

4. **OK**

---

## Após o Ciclo Mensal

O **Dashboard** recalcula automaticamente:
- KPIs (Saldo médio, Numerário, Criptoativos)
- Tabelas de evolução (patrimônio total, por categoria, por plataforma)
- Gráficos

Não precisas de fazer nada manualmente no Dashboard — é tudo fórmulas que puxam de "Dados".

---

## Checklist Mensal

Antes de fechar o mês, verifica:

- [ ] B4 está no número correto do mês (1-12)?
- [ ] Todos os saldos foram preenchidos (coluna F)?
- [ ] "Investido" foi preenchido só para investimentos, não para Conta Principal / Numerário / Bitcoin?
- [ ] Copiei A10:H21 (sem cabeçalho) e colei como valores em "Dados"?
- [ ] Estendi o range da tabela "Dados" para incluir as novas linhas?
- [ ] Dashboard mostra números razoáveis (sem #REF!, #VALOR!, ou valores muito fora)?

---

## Troubleshooting

**P: Ganho/Perda mostra #VALOR! ou está vazio quando devia ter valor?**
- A: Verifica se há um registo anterior desse ativo em "Dados". Se é o primeiro mês, é normal estar vazio.

**P: Dashboard mostra saldos duplicados ou desincronizados com "Dados"?**
- A: Provavelmente o range da tabela "Dados" não foi estendido. Volta a fazer o passo 5.

**P: Copiei e colei, mas as datas/meses ficaram erradas em "Dados"?**
- A: Verifica que usaste "Colar apenas valores" (Ctrl+Shift+V), não um Ctrl+V normal.

---

**Próximo:** Lê `extensao.md` se quiseres adicionar um novo ativo (plataforma de investimento, criptoativo, etc.).
