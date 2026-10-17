"""Base de dados SQLite do PWM.

A base de dados vive FORA do OneDrive (por defeito em %LOCALAPPDATA%\\pwm\\pwm.db):
sincronizar um .db aberto pode gerar conflitos ou corrupção.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2  # 2: registos_mensais.data_leitura

CATEGORIAS = (
    "conta_corrente",
    "transito",
    "emergencia",
    "viagens",
    "p2p",
    "investimento",
    "poupanca",
    "reforma",
    "numerario",
    "cripto",
)

_CATEGORIAS_SQL = ", ".join(f"'{c}'" for c in CATEGORIAS)

# Dia (AAAA-MM-DD) em que o saldo foi lido: o ganho e o aporte semanal da Bondora dependem do dia, não só do mês.
# NULL = registo anterior à versão 2 do esquema. `date(x) = x` rejeita datas impossíveis ('2026-02-30') e
# outros formatos ('13/10/2026', '2026-10-13 10:00'); o COALESCE trata o NULL que date() devolve para lixo.
_COLUNA_DATA_LEITURA = (
    "data_leitura TEXT CHECK (data_leitura IS NULL OR COALESCE(date(data_leitura) = data_leitura, 0))"
)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS plataformas (
    id                INTEGER PRIMARY KEY,
    nome              TEXT    NOT NULL UNIQUE,
    categoria         TEXT    NOT NULL CHECK (categoria IN ({_CATEGORIAS_SQL})),
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
    {_COLUNA_DATA_LEITURA},
    PRIMARY KEY (plataforma_id, mes)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS planos (
    id            INTEGER PRIMARY KEY,
    plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE CASCADE,
    tipo          TEXT    NOT NULL,
    data_inicio   TEXT    NOT NULL
);
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


def _migrar(conn: sqlite3.Connection) -> None:
    """Atualiza uma base criada por uma versão anterior do esquema, sem perder dados."""
    if "data_leitura" not in _colunas(conn, "registos_mensais"):  # versão 1 -> 2
        conn.execute(f"ALTER TABLE registos_mensais ADD COLUMN {_COLUNA_DATA_LEITURA}")


def init_db(conn: sqlite3.Connection) -> None:
    """Cria as tabelas em falta e migra bases antigas. Idempotente. Recusa bases de uma versão futura."""
    versao = conn.execute("PRAGMA user_version").fetchone()[0]
    if versao > SCHEMA_VERSION:
        raise RuntimeError(
            f"A base de dados tem a versão {versao} do esquema, mais recente que a desta aplicação "
            f"({SCHEMA_VERSION}): atualize o código antes de a abrir."
        )
    conn.executescript(SCHEMA)
    _migrar(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
