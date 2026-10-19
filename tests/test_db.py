import sqlite3

import pytest

from app import db


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _plataforma(conn, nome="Degiro", categoria="investimento"):
    cur = conn.execute(
        "INSERT INTO plataformas (nome, categoria, titular) VALUES (?, ?, 'Miguel')",
        (nome, categoria),
    )
    return cur.lastrowid


def test_init_cria_tabelas_e_versao(conn):
    tabelas = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"plataformas", "registos_mensais", "planos", "configuracao"} <= tabelas
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_init_e_idempotente(conn):
    db.init_db(conn)  # segunda vez não pode falhar nem apagar nada
    _plataforma(conn)
    db.init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM plataformas").fetchone()[0] == 1


def test_nome_de_plataforma_unico(conn):
    _plataforma(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _plataforma(conn)


def test_categoria_invalida_rejeitada(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _plataforma(conn, categoria="foguetoes")


def test_registo_unico_por_plataforma_e_mes(conn):
    pid = _plataforma(conn)
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, '2026-10', 10000, 0)",
        (pid,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, '2026-10', 20000, 0)",
            (pid,),
        )


@pytest.mark.parametrize("mau", ["2026-13", "2026-00", "26-10", "2026/10", "2026-1"])
def test_mes_invalido_rejeitado(conn, mau):
    pid = _plataforma(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, ?, 100, 0)",
            (pid, mau),
        )


def test_chave_estrangeira_ativa(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (999, '2026-10', 100, 0)"
        )


def test_nao_apaga_plataforma_com_registos(conn):
    pid = _plataforma(conn)
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, '2026-10', 100, 0)",
        (pid,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM plataformas WHERE id = ?", (pid,))


def test_recusa_base_de_dados_no_onedrive(monkeypatch):
    monkeypatch.delenv("PWM_PERMITIR_ONEDRIVE", raising=False)
    with pytest.raises(RuntimeError):
        db.connect(r"C:\Users\User\OneDrive\Projetos\pwm.db")


def test_caminho_por_defeito_fora_do_onedrive(monkeypatch):
    monkeypatch.delenv("PWM_DB", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\User\AppData\Local")
    assert "onedrive" not in str(db.caminho_por_defeito()).lower()
