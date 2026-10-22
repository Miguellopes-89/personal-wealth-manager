-- Esquema exato da versão 5 (commit b12afdd), gerado por app/db.py dessa versão. Sem dados.
CREATE TABLE categorias (
    codigo TEXT    PRIMARY KEY CHECK (length(codigo) > 0 AND codigo NOT GLOB '*[^a-z0-9_]*'),
    nome   TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(nome)) > 0),
    cor    TEXT    NOT NULL CHECK (cor GLOB '#[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'),
    ordem  INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID;
CREATE TABLE plataformas (
    id                INTEGER PRIMARY KEY,
    nome              TEXT    NOT NULL UNIQUE,
    categoria         TEXT    NOT NULL REFERENCES categorias(codigo) ON DELETE RESTRICT,
    titular           TEXT    NOT NULL,
    finalidade        TEXT,
    plano_mensal_cent INTEGER NOT NULL DEFAULT 0 CHECK (plano_mensal_cent >= 0),
    calcula_ganho     INTEGER NOT NULL DEFAULT 1 CHECK (calcula_ganho IN (0, 1)),
    entra_alocacao    INTEGER NOT NULL DEFAULT 1 CHECK (entra_alocacao IN (0, 1)),
    ativa             INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0, 1)),
    ordem             INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE registos_mensais (
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
CREATE TABLE planos (
    id            INTEGER PRIMARY KEY,
    plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE CASCADE,
    tipo          TEXT    NOT NULL,
    data_inicio   TEXT    NOT NULL
);
CREATE TABLE configuracao (
    chave TEXT    PRIMARY KEY,
    valor INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE depositos_desafio (
    plataforma_id INTEGER NOT NULL,
    domingo       TEXT    NOT NULL CHECK (
        COALESCE(date(domingo) = domingo, 0) AND strftime('%w', domingo) = '0'
    ),
    valor_cent    INTEGER NOT NULL CHECK (valor_cent > 0),
    mes           TEXT    NOT NULL,
    PRIMARY KEY (plataforma_id, domingo),
    FOREIGN KEY (plataforma_id, mes) REFERENCES registos_mensais(plataforma_id, mes) ON DELETE CASCADE
) WITHOUT ROWID;
INSERT INTO categorias VALUES ('conta_corrente', 'Conta corrente', '#8a94a0', 1);
INSERT INTO categorias VALUES ('transito', 'Trânsito', '#b8c0c8', 2);
INSERT INTO categorias VALUES ('emergencia', 'Fundo de liberdade', '#e0a030', 3);
INSERT INTO categorias VALUES ('viagens', 'Viagens', '#2fa4c9', 4);
INSERT INTO categorias VALUES ('p2p', 'P2P', '#7a5bd6', 5);
INSERT INTO categorias VALUES ('investimento', 'Investimento', '#2e8b57', 6);
INSERT INTO categorias VALUES ('poupanca', 'Poupança', '#d2692e', 7);
INSERT INTO categorias VALUES ('reforma', 'Reforma', '#2f5fb3', 8);
INSERT INTO categorias VALUES ('numerario', 'Numerário', '#a98467', 9);
INSERT INTO categorias VALUES ('cripto', 'Cripto', '#c0508a', 10);
PRAGMA user_version = 5;
