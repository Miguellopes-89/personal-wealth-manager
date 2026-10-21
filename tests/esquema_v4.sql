-- Esquema exato da versão 4 (commit ecfd01b), para testar a migração para a v5. Sem dados.

CREATE TABLE IF NOT EXISTS plataformas (
    id                INTEGER PRIMARY KEY,
    nome              TEXT    NOT NULL UNIQUE,
    categoria         TEXT    NOT NULL CHECK (categoria IN ('conta_corrente', 'transito', 'emergencia', 'viagens', 'p2p', 'investimento', 'poupanca', 'reforma', 'numerario', 'cripto')),
    titular           TEXT    NOT NULL,
    finalidade        TEXT,
    plano_mensal_cent INTEGER NOT NULL DEFAULT 0 CHECK (plano_mensal_cent >= 0),
    calcula_ganho     INTEGER NOT NULL DEFAULT 1 CHECK (calcula_ganho IN (0, 1)),
    entra_alocacao    INTEGER NOT NULL DEFAULT 1 CHECK (entra_alocacao IN (0, 1)),
    ativa             INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0, 1)),
    ordem             INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS registos_mensais (
    plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE RESTRICT,
    mes           TEXT    NOT NULL CHECK (
        mes GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
        AND CAST(substr(mes, 6, 2) AS INTEGER) BETWEEN 1 AND 12
    ),
    saldo_cent    INTEGER NOT NULL,
    aporte_cent   INTEGER NOT NULL DEFAULT 0,
    data_leitura TEXT CHECK (data_leitura IS NULL OR COALESCE(date(data_leitura) = data_leitura, 0)),
    PRIMARY KEY (plataforma_id, mes)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS planos (
    id            INTEGER PRIMARY KEY,
    plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE CASCADE,
    tipo          TEXT    NOT NULL,
    data_inicio   TEXT    NOT NULL
);

-- Valores de configuração editáveis na app (ex.: despesa mensal de referência, em cêntimos).
-- Sem CHECK na chave: uma chave nova não obriga a refazer a tabela; as chaves válidas vivem em configuracao.py.
CREATE TABLE IF NOT EXISTS configuracao (
    chave TEXT    PRIMARY KEY,
    valor INTEGER NOT NULL
) WITHOUT ROWID;

-- Depósitos do Desafio das 52 semanas confirmados no check-in: um por domingo e plataforma.
-- `mes` é o check-in (registo mensal) em cujo aporte o depósito entrou; regravar esse mês substitui-os.
-- Um domingo do plano sem linha aqui está "em aberto": volta a aparecer no check-in seguinte.
CREATE TABLE IF NOT EXISTS depositos_desafio (
    plataforma_id INTEGER NOT NULL,
    domingo       TEXT    NOT NULL CHECK (
        COALESCE(date(domingo) = domingo, 0) AND strftime('%w', domingo) = '0'
    ),
    valor_cent    INTEGER NOT NULL CHECK (valor_cent > 0),
    mes           TEXT    NOT NULL,
    PRIMARY KEY (plataforma_id, domingo),
    FOREIGN KEY (plataforma_id, mes) REFERENCES registos_mensais(plataforma_id, mes) ON DELETE CASCADE
) WITHOUT ROWID;
