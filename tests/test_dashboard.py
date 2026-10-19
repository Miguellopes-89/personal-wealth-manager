from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import calc, dashboard, db, planos
from app.main import app

HOJE = date(2026, 10, 19)  # segunda-feira; o último domingo foi 18/10 (42.º de 2026)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _plat(conn, nome, categoria="investimento", plano=0, ganho=1, aloc=1, ativa=1, ordem=0):
    cur = conn.execute(
        """INSERT INTO plataformas
           (nome, categoria, titular, plano_mensal_cent, calcula_ganho, entra_alocacao, ativa, ordem)
           VALUES (?, ?, 'Ana', ?, ?, ?, ?, ?)""",
        (nome, categoria, plano, ganho, aloc, ativa, ordem),
    )
    return cur.lastrowid


def _reg(conn, pid, mes, saldo, aporte=0, data=None):
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) VALUES (?, ?, ?, ?, ?)",
        (pid, mes, saldo, aporte, data),
    )


def _desafio(conn, pid, inicio="2024-01-01"):
    conn.execute(
        "INSERT INTO planos (plataforma_id, tipo, data_inicio) VALUES (?, ?, ?)", (pid, planos.TIPO_DESAFIO_52, inicio)
    )


def _cartao(painel, nome):
    return next(c for c in painel.cartoes if c.nome == nome)


def test_todas_as_categorias_tem_rotulo():
    assert set(dashboard.ROTULOS_CATEGORIA) == set(db.CATEGORIAS)


def test_total_do_desafio_e_1378_euros():
    assert dashboard.TOTAL_DESAFIO_CENT == 137800


def test_sem_registos_nao_ha_painel(conn):
    _plat(conn, "A")
    assert dashboard.construir_painel(conn, HOJE) is None


def test_totais_do_mes(conn):
    a = _plat(conn, "A")  # com ganho
    b = _plat(conn, "B", categoria="conta_corrente", ganho=0, aloc=0)  # só saldo
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, b, "2026-09", 50000)
    _reg(conn, a, "2026-10", 107000, aporte=5000)
    _reg(conn, b, "2026-10", 60000)
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.mes == "2026-10"
    assert painel.totais.patrimonio_cent == 167000
    assert painel.totais.variacao_cent == 17000  # inclui aportes e a plataforma só de saldo
    assert painel.totais.ganho_cent == 2000  # 107000 - 100000 - 5000
    assert _cartao(painel, "B").ganho_cent is None


def test_primeiro_mes_nao_tem_variacao_nem_ganho(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-10", 100000)
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.totais.patrimonio_cent == 100000
    assert painel.totais.variacao_cent is None
    assert painel.totais.ganho_cent is None


def test_plataforma_nao_registada_no_mes_mantem_o_ultimo_saldo(conn):
    a = _plat(conn, "A")
    c = _plat(conn, "C")
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, c, "2026-09", 30000)
    _reg(conn, a, "2026-10", 110000)  # C não foi tocada em outubro
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.totais.patrimonio_cent == 140000
    cartao = _cartao(painel, "C")
    assert (cartao.registado, cartao.saldo_cent, cartao.ganho_cent) == (False, 30000, None)


def test_meses_sem_buracos(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-07", 100000)
    _reg(conn, a, "2026-09", 110000)
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.meses == ("2026-07", "2026-08", "2026-09")
    assert painel.evolucao[0].valores_cent == (100000, 100000, 110000)


def test_meses_atravessam_o_ano(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2025-12", 100000)
    _reg(conn, a, "2026-02", 100000)
    assert dashboard.construir_painel(conn, HOJE).meses == ("2025-12", "2026-01", "2026-02")


def test_plataformas_inativas_ficam_de_fora(conn):
    a = _plat(conn, "A")
    z = _plat(conn, "Z", ativa=0)
    _reg(conn, a, "2026-10", 100000)
    _reg(conn, z, "2026-10", 999999)
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.totais.patrimonio_cent == 100000
    assert [c.nome for c in painel.cartoes] == ["A"]


def test_evolucao_agrupa_por_categoria(conn):
    a = _plat(conn, "A", categoria="investimento")
    b = _plat(conn, "B", categoria="investimento")
    c = _plat(conn, "C", categoria="reforma")
    for pid, saldo in ((a, 100), (b, 200), (c, 400)):
        _reg(conn, pid, "2026-10", saldo)
    painel = dashboard.construir_painel(conn, HOJE)
    series = {s.categoria: s.valores_cent for s in painel.evolucao}
    assert series == {"investimento": (300,), "reforma": (400,)}


def test_alocacao_so_com_plataformas_marcadas_e_por_categoria(conn):
    a = _plat(conn, "A", categoria="investimento")
    b = _plat(conn, "B", categoria="investimento")
    c = _plat(conn, "C", categoria="reforma")
    d = _plat(conn, "D", categoria="numerario", aloc=0, ganho=0)
    for pid, saldo in ((a, 10000), (b, 20000), (c, 70000), (d, 999999)):
        _reg(conn, pid, "2026-10", saldo)
    painel = dashboard.construir_painel(conn, HOJE)
    fatias = {f.categoria: f for f in painel.alocacao}
    assert set(fatias) == {"investimento", "reforma"}
    assert fatias["investimento"].valor_cent == 30000
    assert fatias["investimento"].percentagem == pytest.approx(30.0)
    assert fatias["reforma"].percentagem == pytest.approx(70.0)


def test_alocacao_vazia_se_nao_ha_saldo_nas_plataformas_marcadas(conn):
    d = _plat(conn, "D", categoria="numerario", aloc=0, ganho=0)
    _reg(conn, d, "2026-10", 5000)
    assert dashboard.construir_painel(conn, HOJE).alocacao == ()


def test_plano_mensal_cumprido_e_em_falta(conn):
    ok = _plat(conn, "Ok", plano=5000)
    curto = _plat(conn, "Curto", plano=5000)
    for pid in (ok, curto):
        _reg(conn, pid, "2026-09", 100000)
    _reg(conn, ok, "2026-10", 105000, aporte=5000)
    _reg(conn, curto, "2026-10", 100000, aporte=0)
    painel = dashboard.construir_painel(conn, HOJE)
    assert _cartao(painel, "Ok").em_falta is False
    assert _cartao(painel, "Curto").em_falta is True
    assert _cartao(painel, "Curto").plano_cent == 5000


def test_aporte_acima_do_plano_nao_e_falta(conn):
    a = _plat(conn, "A", plano=5000)
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, a, "2026-10", 110000, aporte=10000)
    assert _cartao(dashboard.construir_painel(conn, HOJE), "A").em_falta is False


def test_saldo_inicial_nao_e_comparado_com_o_plano(conn):
    a = _plat(conn, "A", plano=5000)
    _reg(conn, a, "2026-10", 100000)  # primeiro registo: saldo inicial, sem aporte
    cartao = _cartao(dashboard.construir_painel(conn, HOJE), "A")
    assert (cartao.plano_cent, cartao.em_falta) == (None, False)


def test_plataforma_com_plano_sem_registo_no_mes_fica_por_registar(conn):
    a = _plat(conn, "A", plano=5000)
    b = _plat(conn, "B")  # sem plano
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, b, "2026-09", 100000)
    _reg(conn, b, "2026-10", 100000)
    painel = dashboard.construir_painel(conn, HOJE)
    assert _cartao(painel, "A").por_registar is True
    assert _cartao(painel, "A").em_falta is True
    assert _cartao(painel, "B").em_falta is False


def test_desafio_compara_o_aporte_com_os_domingos_entre_leituras(conn):
    b = _plat(conn, "Bondora", categoria="p2p")
    _desafio(conn, b)
    _reg(conn, b, "2026-10", 500000, data="2026-10-13")
    _reg(conn, b, "2026-11", 513000, aporte=12900, data="2026-11-01")  # domingos 18/10, 25/10 e 1/11: 42+43+44
    painel = dashboard.construir_painel(conn, date(2026, 11, 2))
    cartao = _cartao(painel, "Bondora")
    assert cartao.plano_cent == 12900
    assert cartao.em_falta is False


def test_desafio_com_aporte_a_menos_e_falta(conn):
    b = _plat(conn, "Bondora", categoria="p2p")
    _desafio(conn, b)
    _reg(conn, b, "2026-10", 500000, data="2026-10-13")
    _reg(conn, b, "2026-11", 509000, aporte=8500, data="2026-11-01")  # retirou os 44 € do dia 1/11
    assert _cartao(dashboard.construir_painel(conn, date(2026, 11, 2)), "Bondora").em_falta is True


def test_desafio_sem_datas_nao_compara(conn):
    b = _plat(conn, "Bondora", categoria="p2p")
    _desafio(conn, b)
    _reg(conn, b, "2026-10", 500000)
    _reg(conn, b, "2026-11", 513000, aporte=12900)
    cartao = _cartao(dashboard.construir_painel(conn, date(2026, 11, 2)), "Bondora")
    assert (cartao.plano_cent, cartao.em_falta) == (None, False)


def test_progresso_do_desafio(conn):
    b = _plat(conn, "Bondora", categoria="p2p")
    _desafio(conn, b)
    _reg(conn, b, "2026-10", 500000)
    (progresso,) = dashboard.construir_painel(conn, HOJE).desafios
    assert (progresso.ano, progresso.semana) == (2026, 42)
    assert progresso.previsto_cent == 100 * (42 * 43 // 2)  # 1 + 2 + ... + 42 euros
    assert progresso.total_cent == 137800


def test_progresso_do_desafio_antes_do_primeiro_domingo(conn):
    b = _plat(conn, "Bondora", categoria="p2p")
    _desafio(conn, b)
    _reg(conn, b, "2027-01", 500000)
    (progresso,) = dashboard.construir_painel(conn, date(2027, 1, 2)).desafios  # o 1.º domingo de 2027 é 3/1
    assert (progresso.semana, progresso.previsto_cent) == (0, 0)


def test_desafio_ainda_nao_iniciado_ou_com_data_invalida_nao_aparece(conn):
    a = _plat(conn, "A", categoria="p2p")
    b = _plat(conn, "B", categoria="p2p")
    _desafio(conn, a, inicio="2027-01-01")
    _desafio(conn, b, inicio="lixo")
    _reg(conn, a, "2026-10", 1000)
    _reg(conn, b, "2026-10", 1000)
    assert dashboard.construir_painel(conn, HOJE).desafios == ()


def test_desatualizado_quando_falta_o_mes_atual(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-10", 1000)
    assert dashboard.construir_painel(conn, HOJE).desatualizado is False
    assert dashboard.construir_painel(conn, date(2026, 11, 2)).desatualizado is True


def test_avisos_do_mes_passam_para_o_cartao(conn):
    a = _plat(conn, "A")
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, a, "2026-10", 90000)
    assert _cartao(dashboard.construir_painel(conn, HOJE), "A").avisos == (calc.AVISO_GANHO_NEGATIVO,)


def test_dados_graficos(conn):
    a = _plat(conn, "A", categoria="investimento")
    _reg(conn, a, "2026-09", 100)
    _reg(conn, a, "2026-10", 200)
    dados = dashboard.dados_graficos(dashboard.construir_painel(conn, HOJE))
    assert dados["meses"] == ["2026-09", "2026-10"]
    assert dados["evolucao"] == [{"categoria": "investimento", "rotulo": "Investimento", "valores_cent": [100, 200]}]
    assert dados["alocacao"] == [{"categoria": "investimento", "rotulo": "Investimento", "valor_cent": 200}]


# --- Página web ---------------------------------------------------------------------------


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as c:
        yield c


def _dados_na_base():
    c = db.connect()
    try:
        a = _plat(c, "Corretora Exemplo", categoria="investimento")
        _reg(c, a, "2026-01", 123456)
        c.commit()
    finally:
        c.close()


def test_pagina_inicial_sem_registos(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "Personal Wealth Manager" in r.text
    assert "Ainda não há registos" in r.text
    assert "/sair" in r.text


def test_pagina_inicial_mostra_o_painel(cliente):
    _dados_na_base()
    r = cliente.get("/")
    assert r.status_code == 200
    assert calc.formatar_euros(123456) in r.text
    assert "Corretora Exemplo" in r.text
    assert "/static/vendor/chart.umd.js" in r.text
    assert "https://" not in r.text and "http://" not in r.text  # offline: nada vem de uma CDN
    assert "/sair" in r.text
    assert "O último check-in é de 2026-01" in r.text  # janeiro de 2026 está sempre no passado


def test_static_inexistente_da_404_e_a_pagina_continua_a_funcionar(cliente):
    assert cliente.get("/static/vendor/nao-existe.js").status_code == 404
