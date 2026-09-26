# Setup — Primeiros Passos

## Requisitos

- **LibreOffice Calc 6.0+** (gratuito, multiplataforma) ou **Microsoft Excel 2010+**
- Python 3.8+ (opcional, para validar o ficheiro — ver secção "Validação")

## Download e Instalação

1. **Download do ficheiro template**
   - Descarrega `Personal_Wealth_Manager_template.xlsx` deste repositório

2. **Abre em LibreOffice Calc**
   - Clica duplo no ficheiro, ou abre LibreOffice → Ficheiro → Abrir
   - Se for a primeira vez, LibreOffice pode avisar "Non-standard file format" — escolhe "Use Excel 2010-365 Spreadsheet Format" para manter `.xlsx`

3. **Verifica que as 3 folhas estão lá**
   - Na barra de separadores em baixo, deves ver: **Dashboard** | **Registo Mensal** | **Dados**

## Primeira Utilização

### 1. Preenche a Conta Principal (Janeiro)

Vá para a folha **"Registo Mensal"**:

1. Célula `B3` (Ano): escreve `2026` (ou o ano que queres)
2. Célula `B4` (Mês): escreve `1` (Janeiro)
3. Célula `B5` atualiza-se automaticamente para "Janeiro"

Desce até à linha com "Conta Principal" (deve ser a linha 10):
- **Coluna F (Saldo):** escreve o saldo da tua conta corrente

As outras colunas (Investido, Ganho/Perda) deixas em branco para Conta Principal.

### 2. Preenche um Investimento (ex. Degiro)

Na mesma folha, encontra a linha com "Degiro":
- **Coluna F (Saldo):** escreve o saldo atual
- **Coluna G (Investido):** escreve quanto foi investido (capital próprio introduzido) **este mês** (em Janeiro, provavelmente é 0)
- **Coluna H (Ganho/Perda):** deixa em branco — calcula-se automaticamente (não terá valor em Janeiro, porque é o primeiro mês)

### 3. Preenche Numerário (se aplicável)

Linha "Numerário":
- **Coluna F (Saldo):** escreve o dinheiro físico que tem em casa
- Deixa Investido em branco

### 4. Preenche Bitcoin (se aplicável)

Linha "Bitcoin":
- **Coluna F (Saldo):** escreve o saldo em Bitcoin (ou deixa 0 se não tem)
- Deixa Investido em branco

### 5. Copia os Dados para "Dados"

Agora que preencheste uma linha inteira (Janeiro 2026):

1. **Seleciona A10:H21** (as 12 linhas de ativos, **sem o cabeçalho da linha 9**)
   - Clica em A10 e arrasta até H21, ou usa teclado: A10 → Shift+Ctrl+End
2. **Copia:** Ctrl+C
3. **Vai para a folha "Dados"**
4. **Clica em A2** (primeira linha de dados, após o cabeçalho)
5. **Cola como valores:** Ctrl+Shift+V → escolhe "Colar apenas valores" → OK

Agora tens o teu primeiro mês em "Dados".

### 6. Estende o Range da Tabela "Dados"

A tabela "Dados" tem um range definido que precisa ser atualizado cada vez que adicionas linhas:

1. **Clica dentro da tabela** (qualquer célula entre A1 e H22 agora)
2. **Formatar → Definir Intervalo de Base de Dados** (ou clica direito → Definir Intervalo de Base de Dados)
3. **Novo intervalo:** muda para `Dados.$A$1:$H$22` (ou quantas linhas tenhas agora)
4. **OK**

### 7. Verifica o Dashboard

Vai para a folha **"Dashboard"**:
- Célula `B3` (Ano): deve estar `2026` (copia-se de "Registo Mensal")
- Célula `B4` (Mês): deve estar `1` (Janeiro)
- As tabelas e gráficos devem mostrar os teus dados

Se vires `#REF!` ou `#VALOR!`, volta a "Dados" e verifica que a tabela está com o range correto.

## Próximos Meses

Quando chegares a Fevereiro:

1. **"Registo Mensal":** muda B4 para `2` (Fevereiro)
2. **Preenche saldos novos** (colunas F, G, H atualizam-se automaticamente)
3. **Copia A10:H21**, cola em "Dados" (agora nas linhas 23 em diante)
4. **Estende o range** da tabela "Dados"
5. Repetir ao longo do ano

## Validação (Opcional)

Se tiveres Python instalado, podes validar o ficheiro para certificar que não há erros:

```bash
python3 recalc.py Personal_Wealth_Manager_template.xlsx
```

(Ficheiro `recalc.py` fornecido no repositório, se necessário.)

---

**Próximo:** Lê `workflow-mensal.md` para entender o ciclo mensal em detalhe.
