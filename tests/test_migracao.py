import csv
import sqlite3
from datetime import datetime

import pytest

from app import backup, db, restauro

# Esquema da versão 1 (sem registos_mensais.data_leitura), como está na base real antes da migração.
ESQUEMA_V1 = """
CREATE TABLE plataformas (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL UNIQUE, categoria TEXT NOT NULL, titular TEXT NOT NULL,
    finalidade TEXT, plano_mensal_cent INTEGER NOT NULL DEFAULT 0, calcula_ganho INTEGER NOT NULL DEFAULT 1,
    entra_alocacao INTEGER NOT NULL DEFAULT 1, ativa INTEGER NOT NULL DEFAULT 1, ordem INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE registos_mensais (
    plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE RESTRICT,
    mes TEXT NOT NULL, saldo_cent INTEGER NOT NULL, aporte_cent INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (plataforma_id, mes)
) WITHOUT ROWID;
CREATE TABLE planos (
    id INTEGER PRIMARY KEY, plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL, data_inicio TEXT NOT NULL
);
INSERT INTO plataformas (id, nome, categoria, titular) VALUES (1, 'Bondora Go & Grow', 'p2p', 'Miguel');
INSERT INTO registos_mensais VALUES (1, '2026-10', 500000, 0);
PRAGMA user_version = 1;
"""


def test_base_v1_migra_sem_perder_dados():
    conn = db.connect(":memory:")
    conn.executescript(ESQUEMA_V1)

    db.init_db(conn)

    linha = conn.execute("SELECT * FROM registos_mensais").fetchone()
    assert (linha["plataforma_id"], linha["mes"], linha["saldo_cent"], linha["aporte_cent"]) == (1, "2026-10", 500000, 0)
    assert linha["data_leitura"] is None  # a migração não inventa datas
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    with pytest.raises(sqlite3.IntegrityError):  # a coluna acrescentada também valida a data
        conn.execute("UPDATE registos_mensais SET data_leitura = '2026-02-30'")
    conn.execute("UPDATE registos_mensais SET data_leitura = '2026-10-13'")
    conn.close()


def test_migracao_e_idempotente():
    conn = db.connect(":memory:")
    conn.executescript(ESQUEMA_V1)
    db.init_db(conn)
    conn.execute("UPDATE registos_mensais SET data_leitura = '2026-10-13'")
    db.init_db(conn)  # segunda vez: não falha nem apaga a data
    assert conn.execute("SELECT data_leitura FROM registos_mensais").fetchone()[0] == "2026-10-13"
    conn.close()


def test_base_de_versao_futura_e_recusada():
    conn = db.connect(":memory:")
    conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError, match="mais recente"):
        db.init_db(conn)
    conn.close()


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    c.execute("INSERT INTO plataformas (nome, categoria, titular) VALUES ('Degiro', 'investimento', 'Miguel')")
    yield c
    c.close()


def _inserir(conn, data):
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) "
        "VALUES (1, '2026-10', 100, 0, ?)",
        (data,),
    )


@pytest.mark.parametrize("data", ["2026-10-13", "2028-02-29", None])
def test_data_de_leitura_valida_aceite(conn, data):
    _inserir(conn, data)


@pytest.mark.parametrize(
    "mau", ["2026-02-30", "2026-13-01", "2026-10-00", "13/10/2026", "2026-10-13 10:00", "2026-1-3", "hoje", ""]
)
def test_data_de_leitura_invalida_rejeitada(conn, mau):
    with pytest.raises(sqlite3.IntegrityError):
        _inserir(conn, mau)


def _cortar_ultimas_colunas(ficheiro, n):
    with open(ficheiro, newline="", encoding="utf-8-sig") as f:
        linhas = list(csv.reader(f, delimiter=";"))
    with open(ficheiro, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows([linha[:-n] for linha in linhas])


@pytest.fixture
def copia(conn, tmp_path):
    _inserir(conn, "2026-10-13")
    conn.commit()
    return backup.exportar_csv(conn, tmp_path / "backup", agora=datetime(2026, 10, 14, 9, 0, 0))


def test_restaura_copia_anterior_a_coluna_data_leitura(copia, tmp_path):
    _cortar_ultimas_colunas(copia / "registos_mensais.csv", 1)  # como as cópias feitas na versão 1
    destino = tmp_path / "restaurada.db"

    contagens = restauro.restaurar(copia, destino)

    assert contagens["registos_mensais"] == 1
    nova = db.connect(destino)
    try:
        linha = nova.execute("SELECT saldo_cent, data_leitura FROM registos_mensais").fetchone()
        assert (linha["saldo_cent"], linha["data_leitura"]) == (100, None)
    finally:
        nova.close()


def test_coluna_obrigatoria_em_falta_continua_a_falhar(copia, tmp_path):
    _cortar_ultimas_colunas(copia / "registos_mensais.csv", 2)  # falta aporte_cent, que não é opcional
    destino = tmp_path / "restaurada.db"

    with pytest.raises(ValueError, match="colunas"):
        restauro.restaurar(copia, destino)
    assert not destino.exists()
