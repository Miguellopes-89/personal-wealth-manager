"""Base de dados SQLite do PWM.

A base de dados vive FORA do OneDrive (por defeito em %LOCALAPPDATA%\\pwm\\pwm.db):
sincronizar um .db aberto pode gerar conflitos ou corrupção.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 5
# 2: registos_mensais.data_leitura; 3: tabela configuracao; 4: tabela depositos_desafio;
# 5: tabela categorias (editáveis na app) e plataformas.categoria passa a apontar para ela

# Categorias criadas com a base (ou na migração para a v5): (código, nome no ecrã, cor).
# Depois disso vivem na tabela `categorias` e editam-se na app; o código nunca muda.
CATEGORIAS_BASE = (
    ("conta_corrente", "Conta corrente", "#8a94a0"),
    ("transito", "Trânsito", "#b8c0c8"),
    ("emergencia", "Fundo de liberdade", "#e0a030"),
    ("viagens", "Viagens", "#2fa4c9"),
    ("p2p", "P2P", "#7a5bd6"),
    ("investimento", "Investimento", "#2e8b57"),
    ("poupanca", "Poupança", "#d2692e"),
    ("reforma", "Reforma", "#2f5fb3"),
    ("numerario", "Numerário", "#a98467"),
    ("cripto", "Cripto", "#c0508a"),
)
CATEGORIAS = tuple(c for c, _, _ in CATEGORIAS_BASE)  # códigos de origem (não inclui as criadas na app)

# Desde a v5 a coluna categoria aponta para a tabela categorias; sem isto, a tabela plataformas é antiga
# (até à v4 era uma lista fixa num CHECK; nas primeiras bases nem isso) e é refeita na migração.
_MARCA_V5 = "REFERENCES categorias(codigo)"

# Dia (AAAA-MM-DD) em que o saldo foi lido: o ganho e o aporte semanal da Bondora dependem do dia, não só do mês.
# NULL = registo anterior à versão 2 do esquema. `date(x) = x` rejeita datas impossíveis ('2026-02-30') e
# outros formatos ('13/10/2026', '2026-10-13 10:00'); o COALESCE trata o NULL que date() devolve para lixo.
_COLUNA_DATA_LEITURA = (
    "data_leitura TEXT CHECK (data_leitura IS NULL OR COALESCE(date(data_leitura) = data_leitura, 0))"
)


def _sql_plataformas(tabela: str) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {tabela} (
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
)"""


SCHEMA = f"""
-- Categorias das plataformas. `codigo` é interno e nunca muda (o painel e o fundo de liberdade usam-no);
-- `nome` é o que aparece no ecrã e pode ser renomeado. Nomes repetidos (sem contar maiúsculas) recusados.
CREATE TABLE IF NOT EXISTS categorias (
    codigo TEXT    PRIMARY KEY CHECK (length(codigo) > 0 AND codigo NOT GLOB '*[^a-z0-9_]*'),
    nome   TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(nome)) > 0),
    cor    TEXT    NOT NULL CHECK (cor GLOB '#[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'),
    ordem  INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID;

{_sql_plataformas("plataformas")};

CREATE TABLE IF NOT EXISTS registos_mensais (
    plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE RESTRICT,
    mes           TEXT    NOT NULL CHECK (
        mes GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
        AND CAST(substr(mes, 6, 2) AS INTEGER) BETWEEN 1 AND 12
    ),
    saldo_cent    INTEGER NOT NULL,
    aporte_cent   INTEGER NOT NULL DEFAULT 0,
    {_COLUNA_DATA_LEITURA},
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
"""


def caminho_por_defeito() -> Path:
    env = os.environ.get("PWM_DB")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "pwm" / "pwm.db"


def connect(caminho: str | Path | None = None) -> sqlite3.Connection:
    """Abre a base de dados. Recusa caminhos dentro do OneDrive (decisão de arquitetura)."""
    destino = str(caminho) if caminho is not None else str(caminho_por_defeito())
    if destino != ":memory:":
        # Caminho absoluto e sem atalhos: um PWM_DB relativo ("pwm.db") corrido dentro da pasta do projeto,
        # ou uma ligação simbólica, caía no OneDrive sem a palavra aparecer no texto.
        destino = str(Path(destino).expanduser().resolve())
        if "onedrive" in destino.lower() and not os.environ.get("PWM_PERMITIR_ONEDRIVE"):
            raise RuntimeError(
                f"A base de dados não pode ficar no OneDrive: {destino}. "
                "Use %LOCALAPPDATA%\\pwm\\pwm.db."
            )
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(destino)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = DELETE")  # modo simples: sem ficheiros -wal/-shm
    return conn


def _colunas(conn: sqlite3.Connection, tabela: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabela})")}  # tabela: nome fixo, nunca input


_COLUNAS_PLATAFORMAS = ("id, nome, categoria, titular, finalidade, plano_mensal_cent, calcula_ganho, "
                        "entra_alocacao, ativa, ordem")


def _reconstruir_plataformas(conn: sqlite3.Connection) -> None:
    """4 -> 5: tira o CHECK da lista fixa e liga `categoria` à tabela `categorias`.

    O SQLite não muda restrições de uma coluna: cria-se a tabela nova, copiam-se as linhas (mesmos ids, logo os
    registos, planos e depósitos continuam ligados), apaga-se a antiga e renomeia-se a nova. Tudo numa transação;
    as chaves estrangeiras desligam-se durante a troca (procedimento indicado pelo SQLite) e verificam-se no fim.
    """
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(_sql_plataformas("plataformas_v5"))
        conn.execute(
            f"INSERT INTO plataformas_v5 ({_COLUNAS_PLATAFORMAS}) SELECT {_COLUNAS_PLATAFORMAS} FROM plataformas"
        )
        conn.execute("DROP TABLE plataformas")
        conn.execute("ALTER TABLE plataformas_v5 RENAME TO plataformas")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Migração para a versão 5 abortada: referências inválidas depois de refazer plataformas")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrar(conn: sqlite3.Connection) -> None:
    """Atualiza uma base criada por uma versão anterior do esquema, sem perder dados."""
    if "data_leitura" not in _colunas(conn, "registos_mensais"):  # versão 1 -> 2
        conn.execute(f"ALTER TABLE registos_mensais ADD COLUMN {_COLUNA_DATA_LEITURA}")
    # 2 -> 3 e 3 -> 4: as tabelas configuracao e depositos_desafio são criadas pelo CREATE TABLE IF NOT EXISTS
    # do SCHEMA; uma base antiga fica com elas vazias.
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'plataformas'").fetchone()[0]
    if _MARCA_V5 not in sql:  # 4 -> 5
        _reconstruir_plataformas(conn)


def init_db(conn: sqlite3.Connection) -> None:
    """Cria as tabelas em falta e migra bases antigas. Idempotente. Recusa bases de uma versão futura."""
    versao = conn.execute("PRAGMA user_version").fetchone()[0]
    if versao > SCHEMA_VERSION:
        raise RuntimeError(
            f"A base de dados tem a versão {versao} do esquema, mais recente que a desta aplicação "
            f"({SCHEMA_VERSION}): atualize o código antes de a abrir."
        )
    conn.executescript(SCHEMA)
    if versao < 5:
        # Só ao criar a base ou ao migrar para a v5: uma categoria de origem apagada na app não volta.
        conn.executemany(
            "INSERT OR IGNORE INTO categorias (codigo, nome, cor, ordem) VALUES (?, ?, ?, ?)",
            [(c, n, cor, i) for i, (c, n, cor) in enumerate(CATEGORIAS_BASE, start=1)],
        )
        conn.commit()
    _migrar(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
