# Personal Wealth Manager

Um sistema de rastreamento de finanças pessoais (data structure + fórmulas + dashboards) construído em LibreOffice Calc que demonstra **princípios sólidos de modelação de dados aplicados a um problema real**.

## O Problema

Começava com um ficheiro de referência (`Portefólio.xlsx`) que registava saldos bancários e investimentos mensalmente. A estrutura era:

- **Uma folha por ano** (2023, 2024, 2025)
- **Três colunas por mês** × 12 meses (Saldo | Investido | Ganho/Perda)
- **Linhas para cada ativo** (conta corrente, plataformas de investimento, criptoativos)

**Problema de usabilidade:** Para responder perguntas simples ("Qual o saldo médio da minha conta este ano?" ou "Como evoluiu a alocação entre plataformas?"), tinha de:
- Navegar entre múltiplas folhas
- Somar manualmente colunas espalhadas
- Recriar gráficos cada vez que adicionava dados

**Problema de manutenção:** Adicionar uma nova plataforma de investimento significava duplicar colunas em 12 meses × N folhas — mudança frágil e propensa a erros.

## A Solução: Redesenho Estrutural

### 1. Formato Longo (Tidy Data)

Migrei para uma tabela única com 8 colunas:

```
Ano | Mês | MêsNum | Categoria | Ativo | Saldo | Investido | Ganho/Perda
```

**Por que isto importa:**
- **Uma linha = um registo atómico** (um ativo num mês específico)
- **Adicionar um novo ativo = 1 linha por mês**, não 12 colunas
- **Queries simples:** `SUMIFS(Saldo, Categoria="Investimento", Ano=2026)` vs. somas manuais
- **Escalável:** Se amanhã quiser dados diários, a estrutura não muda

Esta abordagem é padrão em data warehousing (é o princípio de "normalization"), e transporta-se naturalmente para SQL se um dia decidir migrar.

### 2. Categorias Separadas

Criei 4 categorias disjuntas:

| Categoria | Colunas Usadas | Ativos | Nota |
|-----------|---|---|---|
| **Conta Principal** | Saldo | Conta Principal | Dia-a-dia |
| **Investimento** | Saldo + Investido + Ganho/Perda | Activobank, Degiro, XTB, ... | Plataformas de investimento |
| **Numerário** | Saldo | Numerário | Dinheiro físico em casa |
| **Criptoativo** | Saldo | Bitcoin | Acumulado via faucets/airdrops |

**Decisão de design:** Numerário e Criptoativos **não entram no cálculo de alocação** de investimentos (o Dashboard mostra-os em separado). Por quê? Porque semanticamente não são "investimentos" — não há "Investido" associado.

Esta separação reduz ruído na análise e deixa claro o que é uma métrica de "diversificação de portfólio" vs. o que é "caixa disponível".

### 3. Fórmulas Sem Colunas Auxiliares

A coluna `Ganho/Perda` é calculada inline, com uma fórmula complexa mas **reutilizável**.

**O que faz:** Para cada ativo, encontra o **saldo mais recente anterior** e calcula:

```
Ganho/Perda = Saldo Atual − Saldo Anterior − Investido Este Mês
```

**Vantagem:** Sem colunas auxiliares, a tabela mantém-se simples. A lógica está onde é usada, não "escondida" noutro lado. Isto também a torna mais fácil de validar — é tudo visível.

**Trade-off:** A fórmula é complexa, mas é **precisa** e **generalizável** para qualquer lacuna de dados (ex. se um mês não tem registo, a fórmula tolera sem quebrar).

## Estrutura do Ficheiro

```
Personal_Wealth_Manager_template.xlsx
├── Dashboard          [KPIs + gráficos]
├── Registo Mensal     [entrada de dados — workflow mensal]
└── Dados              [tabela longa — histórico completo]
```

### Dashboard

Oferece 4 vistas:

1. **KPIs (top)** — Saldo médio da Conta Principal, Numerário, Criptoativos
2. **Evolução mensal** — Gráfico de linhas: patrimônio total + por categoria ao longo do tempo
3. **Saldo por plataforma** — Série temporal de cada ativo de investimento
4. **Resumo por plataforma** — Tabela: Saldo | Investido Acumulado | Ganho/Perda Acumulado | % Alocação + gráfico de pizza

Todas as tabelas são dinâmicas — alimentadas por `SUMIFS` sobre a tabela "Dados", não por valores hardcoded.

### Registo Mensal

Formulário mensal de entrada:
- **Inputs:** Ano (célula B3), Mês (célula B4)
- **Linhas 10-21:** 12 ativos (Activobank, Degiro, Revolut, etc.)
- **Colunas:** Ano | Mês | MêsNum | Categoria | Ativo | **Saldo** | **Investido** | Ganho/Perda

**Workflow:**
1. Muda B4 para o mês a preencher
2. Preenche os saldos (e "Investido", só em investimentos)
3. Copia A10:H21 (sem cabeçalho), cola como valores em "Dados"
4. Estende o range da tabela "Dados" manualmente

### Dados

Tabela de facto — linha por ativo/mês desde Janeiro 2026. Cabeçalho em linha 1. O ficheiro template começa com apenas o cabeçalho vazio, pronto para receber os teus dados.

## Decisões e Trade-offs Documentados

| Decisão | Vantagem | Custo |
|---------|----------|-------|
| Formato longo | Escalável, SUMIFS simples, padrão da indústria | Menos óbvio à primeira vista |
| Sem colunas auxiliares | Simples, tudo visível | Fórmula de Ganho/Perda é densa |
| Categorias separadas | Sem ruído em análise, semântica clara | Uma coluna extra, um pouco de curador manual |
| LibreOffice Calc | Ferramental acessível, portável | Limitações de performance se > 10k linhas |

## Como Usar

1. **Download** do template (`Personal_Wealth_Manager_template.xlsx`)
2. Abre em LibreOffice Calc (ou Excel)
3. Preenche "Registo Mensal" mês a mês
4. "Dashboard" gera-se automaticamente

Passos detalhados em `docs/workflow-mensal.md`.

## Motivação

Este projeto faz parte do meu portfólio de transição de carreira para **Data Quality/Governance** e **Exploratory Data Analysis**. Demonstra:

- **Modelação de dados:** Decisões arquiteturais (formato longo vs. largo, normalização)
- **Documentação:** Transparência sobre trade-offs e decisões
- **Pragmatismo:** Ferramentas acessíveis (LibreOffice, não SQL) para resolver problemas reais
- **Manutenibilidade:** Estrutura extensível, lógica centralizada em fórmulas

---

**Versão:** Setembro 2026  
**Autor:** Miguel Marques Lopes
