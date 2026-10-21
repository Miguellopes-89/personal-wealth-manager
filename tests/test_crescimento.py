"""Origem do crescimento do património: dinheiro novo (aportes + contas sem ganho), rendimento e plataformas novas.

Regra principal: em cada mês as partes somam exatamente a variação do património (cêntimos inteiros).
Valores fictícios.
"""
import random
from datetime import date

import pytest

from app import dashboard, db

HOJE = date(2026, 10, 19)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _plat(conn, nome, categoria="investimento", ganho=1, ativa=1):
    cur = conn.execute(
        """INSERT INTO plataformas
           (nome, categoria, titular, plano_mensal_cent, calcula_ganho, entra_alocacao, ativa, ordem)
           VALUES (?, ?, 'Ana', 0, ?, 1, ?, 0)""",
        (nome, categoria, ganho, ativa),
    )
    return cur.lastrowid


def _reg(conn, pid, mes, saldo, aporte=0):
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, ?, ?, ?)",
        (pid, mes, saldo, aporte),
    )


def _variacoes(painel):
    total = dashboard.dados_graficos(painel)["total_cent"]
    return [None] + [total[i] - total[i - 1] for i in range(1, len(total))]


def _confere_soma(painel):
    for c, delta in zip(painel.crescimento, _variacoes(painel)):
        if c is None:
            assert delta is None
        else:
            assert c.total_cent == delta, c


def test_primeiro_mes_nao_tem_origem(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-10", 100000)
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.crescimento == (None,)
    assert dashboard.dados_graficos(painel)["crescimento"] == [None]


def test_separa_aportes_contas_sem_ganho_e_rendimento(conn):
    corretora = _plat(conn, "Corretora")
    conta = _plat(conn, "Conta", categoria="conta_corrente", ganho=0)
    _reg(conn, corretora, "2026-09", 100000)
    _reg(conn, conta, "2026-09", 200000)
    # Sai 50 € da conta para a corretora; a conta ainda guarda 300 € do salário; a corretora rende 12,34 €
    _reg(conn, corretora, "2026-10", 106234, aporte=5000)
    _reg(conn, conta, "2026-10", 230000)
    c = dashboard.construir_painel(conn, HOJE).crescimento[1]
    assert (c.mes, c.aportes_cent, c.liquidez_cent, c.rendimento_cent, c.novas_cent) == ("2026-10", 5000, 30000, 1234, 0)
    assert c.dinheiro_novo_cent == 35000
    assert c.total_cent == 36234


def test_despesas_maiores_que_o_salario_dao_dinheiro_novo_negativo(conn):
    corretora = _plat(conn, "Corretora")
    conta = _plat(conn, "Conta", categoria="conta_corrente", ganho=0)
    _reg(conn, corretora, "2026-09", 100000)
    _reg(conn, conta, "2026-09", 200000)
    _reg(conn, corretora, "2026-10", 105000, aporte=5000)
    _reg(conn, conta, "2026-10", 120000)  # gastou 800 € e aportou 50 €
    c = dashboard.construir_painel(conn, HOJE).crescimento[1]
    assert c.dinheiro_novo_cent == -75000
    assert c.rendimento_cent == 0


def test_rendimento_negativo(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, a, "2026-10", 98000, aporte=5000)
    c = dashboard.construir_painel(conn, HOJE).crescimento[1]
    assert (c.aportes_cent, c.rendimento_cent) == (5000, -7000)


def test_levantamento_conta_como_aporte_negativo(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, a, "2026-10", 80300, aporte=-20000)
    c = dashboard.construir_painel(conn, HOJE).crescimento[1]
    assert (c.aportes_cent, c.rendimento_cent) == (-20000, 300)


def test_plataforma_nova_nao_conta_como_dinheiro_novo(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, a, "2026-10", 100000)
    nova = _plat(conn, "Nova")
    _reg(conn, nova, "2026-10", 400000, aporte=1000)  # conta que já existia, registada só agora
    painel = dashboard.construir_painel(conn, HOJE)
    c = painel.crescimento[1]
    assert (c.novas_cent, c.aportes_cent, c.rendimento_cent) == (400000, 0, 0)
    _confere_soma(painel)


def test_plataforma_sem_ganho_nova_tambem_conta_como_nova(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, a, "2026-10", 100000)
    numerario = _plat(conn, "Numerário", categoria="numerario", ganho=0)
    _reg(conn, numerario, "2026-10", 15000)
    c = dashboard.construir_painel(conn, HOJE).crescimento[1]
    assert (c.novas_cent, c.liquidez_cent) == (15000, 0)


def test_mes_sem_registo_fica_a_zero_e_o_seguinte_apanha_os_dois(conn):
    a = _plat(conn, "A")
    b = _plat(conn, "B")
    _reg(conn, a, "2026-08", 100000)
    _reg(conn, b, "2026-08", 50000)
    _reg(conn, b, "2026-09", 51000, aporte=1000)  # A não foi tocada em setembro
    _reg(conn, a, "2026-10", 112000, aporte=10000)  # aporte e ganho de dois meses
    _reg(conn, b, "2026-10", 51000)
    painel = dashboard.construir_painel(conn, HOJE)
    _, setembro, outubro = painel.crescimento
    assert (setembro.aportes_cent, setembro.rendimento_cent) == (1000, 0)
    assert (outubro.aportes_cent, outubro.rendimento_cent) == (10000, 2000)
    _confere_soma(painel)


def test_conta_fechada_sai_como_levantamento(conn):
    a = _plat(conn, "A")
    fechada = _plat(conn, "Fechada", ativa=0)
    _reg(conn, a, "2026-08", 100000)
    _reg(conn, fechada, "2026-08", 30000)
    _reg(conn, fechada, "2026-09", 0, aporte=-30100)  # levantou tudo, com 1 € de juros
    _reg(conn, a, "2026-09", 130100, aporte=30100)
    _reg(conn, a, "2026-10", 130100)
    painel = dashboard.construir_painel(conn, HOJE)
    setembro, outubro = painel.crescimento[1:]
    assert (setembro.aportes_cent, setembro.rendimento_cent) == (0, 100)
    assert outubro.total_cent == 0
    _confere_soma(painel)


def test_partes_somam_sempre_a_variacao_em_dados_aleatorios(conn):
    rng = random.Random(2026)
    meses = [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 11)]
    for n in range(8):
        pid = _plat(conn, f"P{n}", ganho=n % 3 != 0)
        inicio = rng.randrange(0, 8)
        saldo = rng.randrange(0, 1_000_000)
        for mes in meses[inicio:]:
            if rng.random() < 0.2:
                continue  # mês não tocado
            saldo = max(0, saldo + rng.randrange(-50_000, 80_000))
            _reg(conn, pid, mes, saldo, aporte=rng.randrange(-20_000, 30_000))
    painel = dashboard.construir_painel(conn, HOJE)
    assert len(painel.crescimento) == len(painel.meses)
    _confere_soma(painel)


def test_dados_graficos_levam_as_partes_em_centimos(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, a, "2026-10", 106000, aporte=5000)
    dados = dashboard.dados_graficos(dashboard.construir_painel(conn, HOJE))
    assert dados["crescimento"] == [
        None,
        {"aportes_cent": 5000, "liquidez_cent": 0, "rendimento_cent": 1000, "novas_cent": 0},
    ]


# --- Página web ---------------------------------------------------------------------------


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as c:
        yield c


def test_painel_mostra_a_secao_ligada_ao_filtro(cliente):
    c = db.connect()
    try:
        a = _plat(c, "Corretora Exemplo")
        _reg(c, a, "2026-01", 100000)
        _reg(c, a, "2026-02", 106000, aporte=5000)
        c.commit()
    finally:
        c.close()
    r = cliente.get("/")
    assert r.status_code == 200
    assert "De onde veio o crescimento" in r.text
    assert 'id="graf-crescimento"' in r.text and 'id="crescimento-corpo"' in r.text
    assert '"aportes_cent": 5000' in r.text and '"rendimento_cent": 1000' in r.text
    assert "mostrarCrescimento(inicio)" in r.text  # o filtro da evolução também muda esta secção
    # Fora dos formulários com aviso ao sair: ver a secção não conta como alteração por gravar.
    secao = r.text[r.text.index('aria-labelledby="titulo-crescimento"'):r.text.index("<h2>Plataformas</h2>")]
    assert "<form" not in secao and "data-avisar-sair" not in secao


def test_painel_com_um_so_mes_tem_a_secao_sem_partes(cliente):
    c = db.connect()
    try:
        _reg(c, _plat(c, "Corretora Exemplo"), "2026-01", 100000)
        c.commit()
    finally:
        c.close()
    r = cliente.get("/")
    assert r.status_code == 200
    assert '"crescimento": [null]' in r.text
