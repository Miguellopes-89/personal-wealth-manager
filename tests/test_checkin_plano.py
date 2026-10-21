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


def _bondora(conn, com_plano=True):
    cur = conn.execute(
        """INSERT INTO plataformas (nome, categoria, titular, plano_mensal_cent, calcula_ganho)
           VALUES ('Bondora Go & Grow', 'p2p', 'Miguel', 0, 1)"""
    )
    pid = cur.lastrowid
    if com_plano:
        conn.execute(
            "INSERT INTO planos (plataforma_id, tipo, data_inicio) VALUES (?, ?, '2024-01-01')",
            (pid, planos.TIPO_DESAFIO_52),
        )
    conn.commit()
    return pid


def _registo(conn, pid, mes, saldo, aporte=0, data=None):
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) VALUES (?, ?, ?, ?, ?)",
        (pid, mes, saldo, aporte, data),
    )
    conn.commit()


def _data(conn, pid, mes):
    return conn.execute(
        "SELECT data_leitura FROM registos_mensais WHERE plataforma_id = ? AND mes = ?", (pid, mes)
    ).fetchone()[0]


def _n_registos(conn):
    return conn.execute("SELECT COUNT(*) FROM registos_mensais").fetchone()[0]


# --- sugestão do aporte ---------------------------------------------------------------------


def test_aporte_sugerido_pelo_desafio(conn):
    pid = _bondora(conn)
    _registo(conn, pid, "2026-10", 500000, data="2026-10-13")

    linha = checkin.linhas_checkin(conn, "2026-11", date(2026, 11, 1))[0]

    assert linha.aporte_cent == 12900  # semanas 42, 43 e 44
    assert [s.numero for s in linha.sugestao.semanas] == [42, 43, 44]
    assert linha.sugestao.semanas[-1].dia_da_leitura  # 1/11 é domingo e é o dia da leitura
    assert linha.data_leitura_anterior == date(2026, 10, 13)
    assert linha.nota_plano is None


def test_sem_data_da_leitura_nao_ha_sugestao(conn):
    pid = _bondora(conn)
    _registo(conn, pid, "2026-10", 500000, data="2026-10-13")

    linha = checkin.linhas_checkin(conn, "2026-11")[0]

    assert linha.sugestao is None
    assert linha.aporte_cent == 0  # o plano mensal da Bondora
    assert linha.nota_plano is None


def test_leitura_anterior_sem_data_explica_porque_nao_sugere(conn):
    pid = _bondora(conn)
    _registo(conn, pid, "2026-10", 500000)  # registo anterior à versão 2: sem data

    linha = checkin.linhas_checkin(conn, "2026-11", date(2026, 11, 1))[0]

    assert linha.sugestao is None
    assert linha.aporte_cent == 0
    assert "Sem data da leitura anterior" in linha.nota_plano


def test_primeiro_registo_nao_sugere_aporte(conn):
    _bondora(conn)  # saldo inicial: sem leitura anterior, sem aporte a sugerir
    linha = checkin.linhas_checkin(conn, "2026-10", date(2026, 10, 13))[0]
    assert linha.sugestao is None
    assert linha.nota_plano is None
    assert linha.aporte_cent == 0


def test_mes_ja_registado_mantem_o_aporte_gravado(conn):
    pid = _bondora(conn)
    _registo(conn, pid, "2026-10", 500000, data="2026-10-13")
    _registo(conn, pid, "2026-11", 514400, aporte=8500, data="2026-11-01")

    linha = checkin.linhas_checkin(conn, "2026-11", date(2026, 11, 1))[0]

    assert linha.aporte_cent == 8500  # o que ficou gravado, não a sugestão


def test_plataforma_sem_plano_nao_tem_sugestao(conn):
    pid = _bondora(conn, com_plano=False)
    _registo(conn, pid, "2026-10", 500000, data="2026-10-13")
    linha = checkin.linhas_checkin(conn, "2026-11", date(2026, 11, 1))[0]
    assert linha.sugestao is None
    assert linha.nota_plano is None


def test_plano_com_data_de_inicio_invalida_nao_rebenta(conn):
    pid = _bondora(conn, com_plano=False)
    conn.execute(
        "INSERT INTO planos (plataforma_id, tipo, data_inicio) VALUES (?, ?, 'ontem')",
        (pid, planos.TIPO_DESAFIO_52),
    )
    _registo(conn, pid, "2026-10", 500000, data="2026-10-13")
    linha = checkin.linhas_checkin(conn, "2026-11", date(2026, 11, 1))[0]
    assert linha.sugestao is None
    assert "inválida" in linha.nota_plano


# --- gravação da data -----------------------------------------------------------------------


def test_do_saldo_inicial_ao_ganho_de_novembro(conn):
    """Percurso típico: saldo inicial a 13/10, depois o check-in de 1/11 com o aporte sugerido."""
    pid = _bondora(conn)
    r1 = checkin.gravar_checkin(
        conn, "2026-10", [Entrada(pid, "5000,00")], hoje=date(2026, 10, 13), data_leitura=date(2026, 10, 13)
    )
    assert r1.ok
    assert _data(conn, pid, "2026-10") == "2026-10-13"

    linha = checkin.linhas_checkin(conn, "2026-11", date(2026, 11, 1))[0]
    aporte = checkin.cent_para_texto(linha.aporte_cent)  # "129,00"
    r2 = checkin.gravar_checkin(
        conn, "2026-11", [Entrada(pid, "5144,00", aporte)], hoje=date(2026, 11, 1), data_leitura=date(2026, 11, 1)
    )

    assert r2.ok
    assert r2.gravados[0].resultado.ganho_cent == 1500  # 5144,00 - 5000,00 - 129,00
    assert _data(conn, pid, "2026-11") == "2026-11-01"


def test_regravar_atualiza_a_data_e_sem_data_mantem_a_anterior(conn):
    pid = _bondora(conn, com_plano=False)
    hoje = date(2026, 10, 20)
    checkin.gravar_checkin(conn, "2026-10", [Entrada(pid, "100,00")], hoje, data_leitura=date(2026, 10, 13))
    assert _data(conn, pid, "2026-10") == "2026-10-13"

    checkin.gravar_checkin(conn, "2026-10", [Entrada(pid, "101,00")], hoje, data_leitura=date(2026, 10, 15))
    assert _data(conn, pid, "2026-10") == "2026-10-15"

    checkin.gravar_checkin(conn, "2026-10", [Entrada(pid, "102,00")], hoje)  # sem data: não apaga a existente
    assert _data(conn, pid, "2026-10") == "2026-10-15"
    assert _n_registos(conn) == 1


def test_gravar_sem_data_deixa_o_registo_sem_data(conn):
    pid = _bondora(conn, com_plano=False)
    checkin.gravar_checkin(conn, "2026-10", [Entrada(pid, "100,00")], date(2026, 10, 20))
    assert _data(conn, pid, "2026-10") is None


def test_data_fora_do_mes_e_rejeitada_e_nada_e_gravado(conn):
    pid = _bondora(conn, com_plano=False)
    with pytest.raises(ValueError, match="não pertence"):
        checkin.gravar_checkin(
            conn, "2026-10", [Entrada(pid, "100,00")], hoje=date(2026, 11, 5), data_leitura=date(2026, 11, 1)
        )
    assert _n_registos(conn) == 0


def test_data_no_futuro_e_rejeitada(conn):
    pid = _bondora(conn, com_plano=False)
    with pytest.raises(ValueError, match="futuro"):
        checkin.gravar_checkin(
            conn, "2026-10", [Entrada(pid, "100,00")], hoje=date(2026, 10, 13), data_leitura=date(2026, 10, 20)
        )
    assert _n_registos(conn) == 0


# --- data por defeito -----------------------------------------------------------------------


def test_data_por_defeito_no_mes_atual_e_hoje():
    assert checkin.data_por_defeito("2026-10", date(2026, 10, 14)) == date(2026, 10, 14)


def test_data_por_defeito_num_mes_passado_e_o_ultimo_dia():
    assert checkin.data_por_defeito("2026-01", date(2026, 10, 14)) == date(2026, 1, 31)
    assert checkin.data_por_defeito("2028-02", date(2028, 10, 1)) == date(2028, 2, 29)  # bissexto


def test_data_por_defeito_com_mes_invalido():
    with pytest.raises(ValueError):
        checkin.data_por_defeito("2026-13", date(2026, 10, 14))


# --- verificação do rendimento (Bondora) ----------------------------------------------------


def _outubro_e_novembro(conn, aporte, saldo="5144,00", com_plano=True, com_datas=True):
    """Saldo inicial a 13/10 (5000,00 €) e check-in de 1/11 com o saldo e o aporte dados."""
    pid = _bondora(conn, com_plano=com_plano)
    d_out, d_nov = (date(2026, 10, 13), date(2026, 11, 1)) if com_datas else (None, None)
    checkin.gravar_checkin(conn, "2026-10", [Entrada(pid, "5000,00")], hoje=date(2026, 10, 13), data_leitura=d_out)
    return checkin.gravar_checkin(
        conn, "2026-11", [Entrada(pid, saldo, aporte)], hoje=date(2026, 11, 1), data_leitura=d_nov
    )


def test_sem_aviso_de_rendimento_quando_o_aporte_bate_certo(conn):
    r = _outubro_e_novembro(conn, "129,00")  # ganho de 15,00 €: ~5,8 % ao ano
    assert r.gravados[0].avisos_plano == ()


def test_aviso_quando_um_deposito_feito_nao_foi_declarado(conn):
    r = _outubro_e_novembro(conn, "85,00")  # os 44 € de 1/11 entraram no saldo mas ficaram fora do aporte
    avisos = r.gravados[0].avisos_plano
    assert len(avisos) == 2
    assert "22,7 %" in avisos[0]
    assert "diferente da soma dos domingos confirmados (129,00 €)" in avisos[1]


def test_aviso_quando_o_deposito_declarado_nao_chegou(conn):
    r = _outubro_e_novembro(conn, "129,00", saldo="5100,00")  # só chegaram 85 €: o ganho sai negativo
    avisos = r.gravados[0].avisos_plano
    assert len(avisos) == 1
    assert "-11,1 %" in avisos[0]


def test_sem_datas_nao_ha_aviso_de_rendimento(conn):
    r = _outubro_e_novembro(conn, "85,00", com_datas=False)
    assert r.gravados[0].avisos_plano == ()


def test_plataforma_sem_desafio_nao_tem_aviso_de_rendimento(conn):
    r = _outubro_e_novembro(conn, "85,00", com_plano=False)
    assert r.gravados[0].avisos_plano == ()


def test_regravar_linha_igual_mantem_a_data(conn):
    """Corrigir outra plataforma dias depois não muda a data da leitura da Bondora (que não mudou)."""
    pid = _bondora(conn)
    rev = conn.execute(
        "INSERT INTO plataformas (nome, categoria, titular, plano_mensal_cent) VALUES ('Rev', 'viagens', 'X', 2000)"
    ).lastrowid
    conn.commit()
    _registo(conn, pid, "2026-10", 500_000, data="2026-10-13")
    _registo(conn, rev, "2026-10", 10_000, data="2026-10-13")
    checkin.gravar_checkin(
        conn, "2026-11", [Entrada(pid, "5150,00", "129,00"), Entrada(rev, "120,00", "20,00")],
        date(2026, 11, 1), data_leitura=date(2026, 11, 1),
    )
    # 10/11: o ecrã volta a mandar a Bondora igual e a Revolut corrigida
    checkin.gravar_checkin(
        conn, "2026-11", [Entrada(pid, "5150,00", "129,00"), Entrada(rev, "121,00", "20,00")],
        date(2026, 11, 10), data_leitura=date(2026, 11, 10),
    )
    assert _data(conn, pid, "2026-11") == "2026-11-01"
    assert _data(conn, rev, "2026-11") == "2026-11-10"
    dezembro = checkin.linhas_checkin(conn, "2026-12", date(2026, 12, 1))[0]
    assert [s.numero for s in dezembro.sugestao.semanas] == [45, 46, 47, 48]  # o domingo 8/11 não se perde


def test_regravar_linha_igual_sem_data_recebe_a_nova(conn):
    pid = _bondora(conn, com_plano=False)
    _registo(conn, pid, "2026-10", 10_000)
    checkin.gravar_checkin(conn, "2026-10", [Entrada(pid, "100,00")], date(2026, 10, 20), date(2026, 10, 13))
    assert _data(conn, pid, "2026-10") == "2026-10-13"


def test_data_gravada_do_mes(conn):
    pid = _bondora(conn, com_plano=False)
    assert checkin.data_gravada(conn, "2026-10") is None
    _registo(conn, pid, "2026-10", 10_000, data="2026-10-13")
    assert checkin.data_gravada(conn, "2026-10") == date(2026, 10, 13)


def test_verificacao_do_plano_que_rebenta_nao_impede_a_gravacao(conn, monkeypatch):
    pid = _bondora(conn)
    _registo(conn, pid, "2026-10", 500_000, data="2026-10-13")

    def rebenta(*_):
        raise RuntimeError("falha de teste")

    monkeypatch.setattr(checkin, "_avisos_do_plano", rebenta)
    r = checkin.gravar_checkin(conn, "2026-11", [Entrada(pid, "5150,00", "129,00")], date(2026, 11, 1), date(2026, 11, 1))
    assert r.ok
    assert "Não foi possível verificar o rendimento" in r.gravados[0].avisos_plano[0]
    assert _data(conn, pid, "2026-11") == "2026-11-01"
