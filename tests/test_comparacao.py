"""Comparação com índices no painel (v6): rentabilidade ponderada no tempo contra a variação do índice.

Contas feitas à mão, em cêntimos e frações exatas. Valores fictícios.
"""
from datetime import date
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from app import dashboard, db, indices
from app.main import _pct, app

HOJE = date(2026, 3, 15)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _plat(conn, nome, categoria, ganho=1, ativa=1):
    cur = conn.execute(
        "INSERT INTO plataformas (nome, categoria, titular, calcula_ganho, ativa) VALUES (?, ?, 'Ana', ?, ?)",
        (nome, categoria, ganho, ativa),
    )
    return cur.lastrowid


def _reg(conn, pid, mes, saldo_eur, aporte_eur=0):
    conn.execute("INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, ?, ?, ?)",
                 (pid, mes, saldo_eur * 100, aporte_eur * 100))


def _indice(conn, nome, perimetro, valores):
    i = indices.criar(conn, nome, perimetro)
    with conn:
        for mes, v in valores.items():
            indices.gravar_valores(conn, mes, {i: v})
    return i


@pytest.fixture
def base(conn):
    """A e B no investimento (B não é registada em fevereiro), uma conta à ordem sem ganho."""
    a = _plat(conn, "Corretora A", "investimento")
    b = _plat(conn, "Corretora B", "investimento")
    cc = _plat(conn, "Conta", "conta_corrente", ganho=0)
    _reg(conn, a, "2026-01", 1000); _reg(conn, a, "2026-02", 1060, 50); _reg(conn, a, "2026-03", 1100, 50)
    _reg(conn, b, "2026-01", 500); _reg(conn, b, "2026-03", 530)
    _reg(conn, cc, "2026-01", 2000); _reg(conn, cc, "2026-02", 1800); _reg(conn, cc, "2026-03", 1900)
    conn.commit()
    return conn


def _comparacao(conn, nome):
    painel = dashboard.construir_painel(conn, HOJE)
    return next(c for c in painel.comparacoes if c.nome == nome)


def test_rentabilidade_de_uma_categoria(base):
    # fev: A 1050 em jogo (1000 + 50), ganho 10; B não registada: 500 em jogo, rende 0.
    # mar: A 1110 em jogo (1060 + 50), ganho -10; B 500 em jogo, ganho 30 (os dois meses).
    _indice(base, "Ações", "investimento", {"2026-01": 1000000, "2026-03": 1030000})  # sem valor em fevereiro
    c = _comparacao(base, "Ações")
    esperado = (1 + Fraction(1000, 155000)) * (1 + Fraction(2000, 161000)) - 1
    assert (c.tudo.mes_inicio, c.tudo.mes_fim, c.tudo.n_meses) == ("2026-01", "2026-03", 2)
    assert c.tudo.carteira == esperado
    assert c.tudo.indice == Fraction(3, 100)
    assert c.tudo.diferenca_pp == pytest.approx(float((esperado - Fraction(3, 100)) * 100))
    assert c.perimetro_rotulo == "Investimento"
    assert c.ano == c.tudo  # tudo em 2026


def test_rentabilidade_do_patrimonio_todo_conta_o_dinheiro_parado(base):
    # fev: em jogo A 1050 + B 500 + conta 2000 = 3550, ganho 10. mar: 1110 + 500 + 1800 = 3410, ganho 20.
    _indice(base, "Inflação", None, {"2026-01": 1184200, "2026-02": 1186000, "2026-03": 1190000})
    c = _comparacao(base, "Inflação")
    assert c.tudo.carteira == (1 + Fraction(1000, 355000)) * (1 + Fraction(2000, 341000)) - 1
    assert c.tudo.indice == Fraction(1190000, 1184200) - 1
    assert c.perimetro_rotulo == "Património todo"


def test_aportes_nao_contam_como_rendimento(conn):
    a = _plat(conn, "Corretora A", "investimento")
    _reg(conn, a, "2026-01", 1000); _reg(conn, a, "2026-02", 1500, 500)  # só aporte, ganho 0
    conn.commit()
    _indice(conn, "Ações", "investimento", {"2026-01": 1000000, "2026-02": 1000000})
    c = _comparacao(conn, "Ações")
    assert c.tudo.carteira == 0 and c.tudo.diferenca_pp == 0


def test_faltam_dados_com_um_so_valor_do_indice(base):
    _indice(base, "Ações", "investimento", {"2026-03": 1030000})
    c = _comparacao(base, "Ações")
    assert c.tudo is None and c.ano is None


def test_este_ano_comeca_no_primeiro_valor_do_ano(conn):
    a = _plat(conn, "Corretora A", "investimento")
    for mes, saldo in (("2025-11", 1000), ("2025-12", 1010), ("2026-01", 1020), ("2026-02", 1040)):
        _reg(conn, a, mes, saldo)
    conn.commit()
    _indice(conn, "Ações", "investimento", {"2025-11": 1000000, "2026-01": 1010000, "2026-02": 1030000})
    c = _comparacao(conn, "Ações")
    assert (c.tudo.mes_inicio, c.tudo.mes_fim) == ("2025-11", "2026-02")
    assert c.tudo.carteira == Fraction(40, 1000)  # sem aportes, a rentabilidade encadeada é a variação do saldo
    assert (c.ano.mes_inicio, c.ano.mes_fim) == ("2026-01", "2026-02")
    assert c.ano.carteira == Fraction(20, 1020) and c.ano.indice == Fraction(1030000, 1010000) - 1


def test_perimetro_sem_dinheiro_no_inicio_comeca_mais_tarde(conn):
    cc = _plat(conn, "Conta", "conta_corrente", ganho=0)
    _reg(conn, cc, "2026-01", 2000); _reg(conn, cc, "2026-02", 2000); _reg(conn, cc, "2026-03", 2000)
    a = _plat(conn, "Corretora A", "investimento")
    _reg(conn, a, "2026-02", 1000); _reg(conn, a, "2026-03", 1020)  # nova em fevereiro
    conn.commit()
    _indice(conn, "Ações", "investimento", {"2026-01": 1000000, "2026-02": 1010000, "2026-03": 1030000})
    c = _comparacao(conn, "Ações")
    assert (c.tudo.mes_inicio, c.tudo.mes_fim) == ("2026-02", "2026-03")
    assert c.tudo.carteira == Fraction(20, 1000)


def test_indice_inativo_fica_de_fora(base):
    i = _indice(base, "Velho", None, {"2026-01": 10000, "2026-03": 20000})
    indices.definir_ativo(base, i, False)
    assert dashboard.construir_painel(base, HOJE).comparacoes == ()


def test_so_anualiza_a_partir_de_12_meses(conn):
    a = _plat(conn, "Corretora A", "investimento")
    saldo = 1000
    for n in range(13):  # 2025-01 a 2026-01, +1 € por mês
        _reg(conn, a, f"{2025 + n // 12}-{n % 12 + 1:02d}", saldo + n)
    conn.commit()
    _indice(conn, "Ações", "investimento", {"2025-01": 1000000, "2025-07": 1050000, "2026-01": 1100000})
    c = _comparacao(conn, "Ações")
    assert c.tudo.n_meses == 12
    assert c.tudo.indice_ano_pct == pytest.approx(10.0)
    assert c.tudo.carteira_ano_pct == pytest.approx(1.2)
    assert c.ano is None  # em 2026 só há um valor


@pytest.mark.parametrize("valor, texto", [(1.234, "+1,23 %"), (-0.5, "−0,50 %"), (0.0, "0,00 %"), (-0.001, "0,00 %")])
def test_formato_das_percentagens(valor, texto):
    assert _pct(valor) == texto


def test_painel_mostra_a_seccao(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as cliente:
        conn = db.connect()
        a = _plat(conn, "Corretora A", "investimento")
        _reg(conn, a, "2026-01", 1000); _reg(conn, a, "2026-02", 1010)
        conn.commit()
        r = cliente.get("/")
        assert "Comparação com índices" in r.text and "Ainda não há índices ativos" in r.text

        _indice(conn, "Ações mundo", "investimento", {"2026-01": 1000000, "2026-02": 1020000})
        _indice(conn, "Inflação", None, {"2026-02": 1184200})
        conn.close()
        r = cliente.get("/")
        assert "Ações mundo" in r.text and "+1,00 %" in r.text and "+2,00 %" in r.text and "−1,00 p.p." in r.text
        assert "Faltam dados" in r.text  # a inflação só tem um valor
        assert 'data-periodo-bloco="ano" hidden' in r.text
