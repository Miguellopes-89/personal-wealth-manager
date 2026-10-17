from datetime import date

import pytest

from app import calc, checkin, db
from app.checkin import Entrada

HOJE = date(2026, 10, 13)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _criar(conn, nome, plano=0, ganho=1, ativa=1, ordem=0):
    cur = conn.execute(
        """INSERT INTO plataformas
           (nome, categoria, titular, plano_mensal_cent, calcula_ganho, ativa, ordem)
           VALUES (?, 'poupanca', 'Miguel', ?, ?, ?, ?)""",
        (nome, plano, ganho, ativa, ordem),
    )
    conn.commit()
    return cur.lastrowid


def _registo(conn, pid, mes, saldo, aporte=0):
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, ?, ?, ?)",
        (pid, mes, saldo, aporte),
    )
    conn.commit()


def _n_registos(conn):
    return conn.execute("SELECT COUNT(*) FROM registos_mensais").fetchone()[0]


# --- validar_mes ---------------------------------------------------------------

def test_validar_mes_aceita_o_mes_atual_e_passados():
    checkin.validar_mes("2026-10", HOJE)
    checkin.validar_mes("2025-01", HOJE)


def test_validar_mes_rejeita_futuro():
    with pytest.raises(ValueError, match="futuro"):
        checkin.validar_mes("2026-11", HOJE)


@pytest.mark.parametrize("mau", ["2026-13", "2026-1", "26-10", "outubro", ""])
def test_validar_mes_rejeita_formato_invalido(mau):
    with pytest.raises(ValueError):
        checkin.validar_mes(mau, HOJE)


# --- linhas_checkin ------------------------------------------------------------

def test_linhas_sugerem_o_aporte_do_plano_e_nao_pre_preenchem_saldo(conn):
    rev = _criar(conn, "Revolut", plano=2000)
    linhas = checkin.linhas_checkin(conn, "2026-10")
    assert len(linhas) == 1
    l = linhas[0]
    assert l.plataforma_id == rev
    assert l.aporte_cent == 2000
    assert l.saldo_cent is None
    assert l.registado is False
    assert l.saldo_anterior_cent is None and l.mes_anterior is None


def test_linhas_mostram_o_ultimo_registo_anterior_como_referencia(conn):
    rev = _criar(conn, "Revolut", plano=2000)
    _registo(conn, rev, "2026-08", 10000)
    _registo(conn, rev, "2026-09", 12000)
    _registo(conn, rev, "2026-11", 99999)  # posterior: não conta como anterior
    l = checkin.linhas_checkin(conn, "2026-10")[0]
    assert l.mes_anterior == "2026-09"
    assert l.saldo_anterior_cent == 12000


def test_linhas_mostram_os_valores_ja_registados_no_mes(conn):
    rev = _criar(conn, "Revolut", plano=2000)
    _registo(conn, rev, "2026-10", 15000, aporte=500)
    l = checkin.linhas_checkin(conn, "2026-10")[0]
    assert l.registado is True
    assert l.saldo_cent == 15000
    assert l.aporte_cent == 500  # o registado, não o plano


def test_linhas_so_incluem_ativas_pela_ordem_definida(conn):
    _criar(conn, "B", ordem=2)
    _criar(conn, "A", ordem=1)
    _criar(conn, "Inativa", ordem=0, ativa=0)
    assert [l.nome for l in checkin.linhas_checkin(conn, "2026-10")] == ["A", "B"]


# --- gravar_checkin ------------------------------------------------------------

def test_primeiro_registo_e_saldo_inicial_sem_ganho(conn):
    rev = _criar(conn, "Revolut", plano=2000)
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(rev, "100,00", "20,00")], HOJE)
    assert r.ok
    assert r.gravados[0].resultado.ganho_cent is None
    row = conn.execute("SELECT saldo_cent, aporte_cent FROM registos_mensais").fetchone()
    assert (row["saldo_cent"], row["aporte_cent"]) == (10000, 2000)


def test_ganho_do_mes_e_saldo_menos_anterior_menos_aporte(conn):
    rev = _criar(conn, "Revolut")
    _registo(conn, rev, "2026-09", 100000)
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(rev, "1.050,00", "20,00")], HOJE)
    assert r.gravados[0].resultado.ganho_cent == 3000  # 1050 - 1000 - 20 = 30 €
    assert r.gravados[0].resultado.avisos == ()


def test_ganho_negativo_gera_aviso(conn):
    rev = _criar(conn, "Revolut")
    _registo(conn, rev, "2026-09", 100000)
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(rev, "900,00", "")], HOJE)
    res = r.gravados[0].resultado
    assert res.ganho_cent == -10000
    assert calc.AVISO_GANHO_NEGATIVO in res.avisos


def test_mes_em_falta_gera_aviso(conn):
    rev = _criar(conn, "Revolut")
    _registo(conn, rev, "2026-08", 100000)
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(rev, "1010,00")], HOJE)
    res = r.gravados[0].resultado
    assert res.ganho_cent == 1000
    assert calc.AVISO_MES_EM_FALTA in res.avisos


def test_plataforma_sem_ganho_nao_calcula_ganho(conn):
    conta = _criar(conn, "Conta Principal", ganho=0)
    _registo(conn, conta, "2026-09", 100000)
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(conta, "2000,00")], HOJE)
    assert r.gravados[0].resultado.ganho_cent is None
    assert r.gravados[0].resultado.avisos == ()


def test_saldo_em_branco_nao_grava_e_fica_ignorado(conn):
    a = _criar(conn, "A")
    b = _criar(conn, "B")
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(a, "50,00"), Entrada(b, "  ")], HOJE)
    assert r.ok
    assert r.ignorados == (b,)
    assert _n_registos(conn) == 1


def test_aporte_em_branco_conta_como_zero(conn):
    a = _criar(conn, "A", plano=5000)
    checkin.gravar_checkin(conn, "2026-10", [Entrada(a, "50,00", "")], HOJE)
    assert conn.execute("SELECT aporte_cent FROM registos_mensais").fetchone()[0] == 0


def test_gravacao_e_tudo_ou_nada(conn):
    a = _criar(conn, "A")
    b = _criar(conn, "B")
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(a, "50,00"), Entrada(b, "abc")], HOJE)
    assert not r.ok
    assert b in r.erros and a not in r.erros
    assert _n_registos(conn) == 0  # nem a linha válida foi gravada


def test_valor_ambiguo_e_rejeitado(conn):
    a = _criar(conn, "A")
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(a, "1.234")], HOJE)
    assert not r.ok
    assert "ambíguo" in r.erros[a]
    assert _n_registos(conn) == 0


def test_regravar_o_mes_atualiza_sem_duplicar(conn):
    a = _criar(conn, "A")
    checkin.gravar_checkin(conn, "2026-10", [Entrada(a, "100,00", "0")], HOJE)
    checkin.gravar_checkin(conn, "2026-10", [Entrada(a, "120,00", "10,00")], HOJE)
    assert _n_registos(conn) == 1
    row = conn.execute("SELECT saldo_cent, aporte_cent FROM registos_mensais").fetchone()
    assert (row["saldo_cent"], row["aporte_cent"]) == (12000, 1000)


def test_mes_futuro_nao_grava(conn):
    a = _criar(conn, "A")
    with pytest.raises(ValueError, match="futuro"):
        checkin.gravar_checkin(conn, "2026-11", [Entrada(a, "100,00")], HOJE)
    assert _n_registos(conn) == 0


def test_plataforma_inativa_ou_desconhecida_e_erro(conn):
    inativa = _criar(conn, "Inativa", ativa=0)
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(inativa, "10,00"), Entrada(999, "10,00")], HOJE)
    assert set(r.erros) == {inativa, 999}
    assert _n_registos(conn) == 0


def test_plataforma_repetida_no_formulario_e_erro(conn):
    a = _criar(conn, "A")
    r = checkin.gravar_checkin(conn, "2026-10", [Entrada(a, "10,00"), Entrada(a, "20,00")], HOJE)
    assert not r.ok
    assert _n_registos(conn) == 0
