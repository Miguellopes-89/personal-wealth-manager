"""Depósitos do Desafio das 52 semanas confirmados no check-in (esquema v4).

Valores fictícios. O cenário-base imita o arranque da app: saldo inicial lido a 13/10/2026 e o check-in
seguinte a 1/11/2026 (domingos 18/10, 25/10 e 1/11 = semanas 42, 43 e 44).
"""
from datetime import date

import pytest

from app import checkin, db, planos
from app.checkin import Entrada


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _p2p(conn, data_inicial="2026-10-13"):
    pid = conn.execute(
        "INSERT INTO plataformas (nome, categoria, titular) VALUES ('P2P Teste', 'p2p', 'Ana')"
    ).lastrowid
    conn.execute(
        "INSERT INTO planos (plataforma_id, tipo, data_inicio) VALUES (?, ?, '2024-01-01')",
        (pid, planos.TIPO_DESAFIO_52),
    )
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) "
        "VALUES (?, '2026-10', 500000, 0, ?)",
        (pid, data_inicial),
    )
    conn.commit()
    return pid


def _depositos(conn, pid):
    return [
        (r["domingo"], r["valor_cent"], r["mes"])
        for r in conn.execute("SELECT * FROM depositos_desafio WHERE plataforma_id = ? ORDER BY domingo", (pid,))
    ]


def _novembro(conn, pid, domingos, aporte="129,00", saldo="5145,00", data=date(2026, 11, 1), hoje=None):
    return checkin.gravar_checkin(
        conn, "2026-11", [Entrada(pid, saldo, aporte, domingos)], hoje or data, data_leitura=data
    )


def _linha(conn, mes, data):
    return checkin.linhas_checkin(conn, mes, data)[0]


# --- domingos em aberto ----------------------------------------------------------------------


def test_primeiro_checkin_mostra_as_semanas_desde_o_saldo_inicial_todas_marcadas(conn):
    _p2p(conn)
    linha = _linha(conn, "2026-11", date(2026, 11, 1))
    assert [s.numero for s in linha.sugestao.semanas] == [42, 43, 44]
    assert linha.domingos_marcados == {date(2026, 10, 18), date(2026, 10, 25), date(2026, 11, 1)}
    assert not any(s.em_atraso for s in linha.sugestao.semanas)
    assert linha.aporte_cent == 12900


def test_semanas_anteriores_ao_saldo_inicial_nunca_aparecem(conn):
    _p2p(conn)  # o saldo de 13/10 já inclui as semanas 1 a 41
    linha = _linha(conn, "2026-11", date(2026, 11, 1))
    assert min(s.numero for s in linha.sugestao.semanas) == 42


def test_domingo_desmarcado_volta_no_mes_seguinte_em_atraso(conn):
    pid = _p2p(conn)
    r = _novembro(conn, pid, ("2026-10-18", "2026-10-25"), aporte="85,00", saldo="5106,00")
    assert r.ok
    assert _depositos(conn, pid) == [("2026-10-18", 4200, "2026-11"), ("2026-10-25", 4300, "2026-11")]

    dezembro = _linha(conn, "2026-12", date(2026, 12, 1))

    assert [s.numero for s in dezembro.sugestao.semanas] == [44, 45, 46, 47, 48]
    assert [s.em_atraso for s in dezembro.sugestao.semanas] == [True, False, False, False, False]
    assert dezembro.aporte_cent == 100 * (44 + 45 + 46 + 47 + 48)


def test_domingos_confirmados_noutro_mes_nao_voltam(conn):
    pid = _p2p(conn)
    _novembro(conn, pid, ("2026-10-18", "2026-10-25", "2026-11-01"))
    dezembro = _linha(conn, "2026-12", date(2026, 12, 1))
    assert [s.numero for s in dezembro.sugestao.semanas] == [45, 46, 47, 48]


def test_mes_ja_registado_mostra_marcado_so_o_confirmado(conn):
    pid = _p2p(conn)
    _novembro(conn, pid, ("2026-10-18",), aporte="42,00", saldo="5050,00")
    linha = _linha(conn, "2026-11", date(2026, 11, 1))
    assert [s.numero for s in linha.sugestao.semanas] == [42, 43, 44]  # continuam na lista para se marcarem
    assert linha.domingos_marcados == {date(2026, 10, 18)}


def test_primeiro_registo_sem_data_conta_so_desde_a_leitura_anterior(conn):
    pid = _p2p(conn, data_inicial=None)
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) "
        "VALUES (?, '2026-11', 510000, 0, '2026-11-01')",
        (pid,),
    )
    conn.commit()
    linha = _linha(conn, "2026-12", date(2026, 12, 1))
    assert [s.numero for s in linha.sugestao.semanas] == [45, 46, 47, 48]


# --- gravação ----------------------------------------------------------------------------------


def test_caixas_marcadas_ficam_gravadas_com_o_valor_do_plano(conn):
    pid = _p2p(conn)
    r = _novembro(conn, pid, ("2026-10-18", "2026-10-25", "2026-11-01"))
    assert r.ok and r.gravados[0].avisos_plano == ()
    assert _depositos(conn, pid) == [
        ("2026-10-18", 4200, "2026-11"), ("2026-10-25", 4300, "2026-11"), ("2026-11-01", 4400, "2026-11"),
    ]


def test_regravar_o_mes_substitui_as_confirmacoes(conn):
    pid = _p2p(conn)
    _novembro(conn, pid, ("2026-10-18", "2026-10-25", "2026-11-01"))
    r = _novembro(conn, pid, ("2026-10-18", "2026-10-25"), aporte="85,00", saldo="5106,00")
    assert r.ok
    assert [d for d, _, _ in _depositos(conn, pid)] == ["2026-10-18", "2026-10-25"]


def test_sem_caixas_marcadas_nao_confirma_nada(conn):
    pid = _p2p(conn)
    r = _novembro(conn, pid, (), aporte="0,00", saldo="5021,00")
    assert r.ok
    assert _depositos(conn, pid) == []


def test_chamada_sem_informacao_das_caixas_confirma_todos(conn):
    pid = _p2p(conn)
    _novembro(conn, pid, None)
    assert len(_depositos(conn, pid)) == 3


@pytest.mark.parametrize("mau", ["2026-10-11", "2026-11-08", "2026-10-19", "lixo", ""])
def test_domingo_fora_dos_em_aberto_recusa_tudo(conn, mau):
    pid = _p2p(conn)
    r = _novembro(conn, pid, ("2026-10-18", mau))
    assert not r.ok and pid in r.erros
    assert _depositos(conn, pid) == []
    assert conn.execute("SELECT COUNT(*) FROM registos_mensais WHERE mes = '2026-11'").fetchone()[0] == 0


def test_domingo_ja_confirmado_noutro_mes_e_recusado(conn):
    pid = _p2p(conn)
    _novembro(conn, pid, ("2026-10-18", "2026-10-25", "2026-11-01"))
    r = checkin.gravar_checkin(
        conn, "2026-12", [Entrada(pid, "5400,00", "42,00", ("2026-10-18",))],
        date(2026, 12, 1), data_leitura=date(2026, 12, 1),
    )
    assert not r.ok
    assert [m for _, _, m in _depositos(conn, pid)] == ["2026-11"] * 3


def test_caixas_repetidas_contam_uma_vez(conn):
    pid = _p2p(conn)
    r = _novembro(conn, pid, ("2026-10-18", "2026-10-18"), aporte="42,00", saldo="5050,00")
    assert r.ok
    assert _depositos(conn, pid) == [("2026-10-18", 4200, "2026-11")]


def test_saldo_em_branco_nao_mexe_nas_confirmacoes(conn):
    pid = _p2p(conn)
    _novembro(conn, pid, ("2026-10-18",), aporte="42,00", saldo="5050,00")
    r = _novembro(conn, pid, (), saldo="", aporte="")
    assert r.ok and r.ignorados == (pid,)
    assert len(_depositos(conn, pid)) == 1


def test_aviso_quando_o_aporte_nao_bate_com_as_caixas(conn):
    pid = _p2p(conn)
    r = _novembro(conn, pid, ("2026-10-18", "2026-10-25"), aporte="129,00")
    avisos = r.gravados[0].avisos_plano
    assert any("diferente da soma dos domingos confirmados (85,00 €)" in a for a in avisos)


def test_regravar_linha_igual_usa_a_data_gravada(conn):
    """Uma linha igual mantém a data de 1/11: o domingo 8/11 não pode ser confirmado em novembro."""
    pid = _p2p(conn)
    _novembro(conn, pid, ("2026-10-18", "2026-10-25", "2026-11-01"))
    r = _novembro(conn, pid, ("2026-10-18", "2026-10-25", "2026-11-01"), data=date(2026, 11, 10))
    assert r.ok
    dezembro = _linha(conn, "2026-12", date(2026, 12, 1))
    assert [s.numero for s in dezembro.sugestao.semanas] == [45, 46, 47, 48]


def test_plataforma_sem_desafio_com_caixas_e_recusada(conn):
    pid = conn.execute(
        "INSERT INTO plataformas (nome, categoria, titular, plano_mensal_cent) VALUES ('Viagens', 'viagens', 'Ana', 2000)"
    ).lastrowid
    conn.execute("INSERT INTO registos_mensais VALUES (?, '2026-10', 1000, 0, '2026-10-13')", (pid,))
    conn.commit()
    r = checkin.gravar_checkin(
        conn, "2026-11", [Entrada(pid, "30,00", "20,00", ("2026-10-18",))], date(2026, 11, 1), date(2026, 11, 1)
    )
    assert not r.ok
