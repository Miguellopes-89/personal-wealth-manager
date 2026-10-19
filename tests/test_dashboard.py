from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import calc, configuracao, dashboard, db, planos
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


def test_inativa_sem_registo_no_mes_fica_de_fora_do_mes_mas_nao_do_passado(conn):
    """Opção A (19/10/2026): desativar não reescreve o passado; depois do último registo deixa de contar."""
    a = _plat(conn, "A")
    z = _plat(conn, "Z", ativa=0)
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, z, "2026-09", 50000)
    _reg(conn, a, "2026-10", 100000)
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.totais.patrimonio_cent == 100000
    assert [c.nome for c in painel.cartoes] == ["A"]
    evolucao = {s.categoria: s.valores_cent for s in painel.evolucao}
    assert evolucao["investimento"] == (150000, 100000)


def test_conta_fechada_no_mes_mantem_a_variacao_e_o_ganho_certos(conn):
    """Fechar a Z (levantamento de 500 € para a A) não é perda: variação 0 e ganho só o real."""
    a = _plat(conn, "A")
    z = _plat(conn, "Z", ativa=0)
    _reg(conn, a, "2026-09", 100000)
    _reg(conn, z, "2026-09", 50000)
    _reg(conn, a, "2026-10", 150300, aporte=50000)  # recebeu os 500 € e ganhou 3 €
    _reg(conn, z, "2026-10", 0, aporte=-50000)  # fecho registado à mão no check-in: saldo 0 e levantamento
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.totais.patrimonio_cent == 150300
    assert painel.totais.variacao_cent == 300
    assert painel.totais.ganho_cent == 300
    assert [c.nome for c in painel.cartoes] == ["A"]


def test_inativa_fora_da_alocacao_e_dos_planos(conn):
    a = _plat(conn, "A")
    z = _plat(conn, "Z", ativa=0)
    _desafio(conn, z)
    _reg(conn, a, "2026-10", 100000)
    _reg(conn, z, "2026-10", 999999)
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.totais.patrimonio_cent == 100000 + 999999  # registo no mês: conta no património
    assert sum(f.valor_cent for f in painel.alocacao) == 100000
    assert painel.desafios == ()


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
    assert "O último check-in é de 01-2026" in r.text  # janeiro de 2026 está sempre no passado


def test_static_inexistente_da_404_e_a_pagina_continua_a_funcionar(cliente):
    assert cliente.get("/static/vendor/nao-existe.js").status_code == 404


def test_categoria_emergencia_aparece_como_fundo_de_liberdade():
    assert dashboard.ROTULOS_CATEGORIA["emergencia"] == "Fundo de liberdade"
    assert not any("emergência" in r.lower() for r in dashboard.ROTULOS_CATEGORIA.values())


def test_painel_mostra_meses_como_mm_aaaa(cliente):
    _dados_na_base()
    r = cliente.get("/")
    assert "Dados de 01-2026" in r.text
    assert "legend: { display: false }" in r.text  # donut: a legenda fica só na lista por baixo


# --- Fundo de liberdade --------------------------------------------------------------------


def test_sem_plataforma_do_fundo_nao_ha_cobertura(conn):
    a = _plat(conn, "Corretora")
    _reg(conn, a, "2026-09", 100000)
    assert dashboard.construir_painel(conn, HOJE).cobertura is None


def test_cobertura_sem_referencia_mostra_so_o_saldo(conn):
    f = _plat(conn, "Fundo", categoria="emergencia", aloc=0)
    _reg(conn, f, "2026-09", 300000)
    cob = dashboard.construir_painel(conn, HOJE).cobertura
    assert cob.saldo_cent == 300000
    assert cob.despesa_mensal_cent is None and cob.meses is None


def test_cobertura_soma_as_contas_do_fundo_no_mes_do_painel(conn):
    f1 = _plat(conn, "Fundo A", categoria="emergencia", aloc=0)
    f2 = _plat(conn, "Fundo B", categoria="emergencia", aloc=0)
    outra = _plat(conn, "Corretora")
    _reg(conn, f1, "2026-08", 100000)
    _reg(conn, f1, "2026-09", 200000)
    _reg(conn, f2, "2026-08", 100000)  # sem registo em setembro: conta com o último saldo
    _reg(conn, outra, "2026-09", 999900)
    configuracao.definir_despesa_mensal(conn, 150000)

    cob = dashboard.construir_painel(conn, HOJE).cobertura

    assert cob.saldo_cent == 300000
    assert cob.meses == 2.0


def test_cobertura_com_conta_do_fundo_fechada(conn):
    """Uma conta do fundo fechada (saldo 0, inativa) não infla nem anula a cobertura."""
    fechada = _plat(conn, "Fundo antigo", categoria="emergencia", aloc=0, ativa=0)
    nova = _plat(conn, "Fundo novo", categoria="emergencia", aloc=0)
    _reg(conn, fechada, "2026-08", 0, aporte=-100000)
    _reg(conn, nova, "2026-08", 100000, aporte=100000)
    _reg(conn, nova, "2026-09", 100100)
    configuracao.definir_despesa_mensal(conn, 100000)
    assert dashboard.construir_painel(conn, HOJE).cobertura.saldo_cent == 100100


def test_pagina_mostra_cobertura_em_meses(cliente):
    c = db.connect()
    try:
        f = _plat(c, "Fundo Exemplo", categoria="emergencia", aloc=0)
        _reg(c, f, "2026-01", 1234500)
        c.commit()
        configuracao.definir_despesa_mensal(c, 98000)
    finally:
        c.close()
    r = cliente.get("/")
    assert "12,6 meses" in r.text
    assert calc.formatar_euros(98000) in r.text
    assert 'value="980,00"' in r.text


def test_gravar_despesa_pelo_painel(cliente, monkeypatch, tmp_path):
    copias = tmp_path / "copias"
    monkeypatch.setenv("PWM_BACKUP", str(copias))
    c = db.connect()
    try:
        f = _plat(c, "Fundo Exemplo", categoria="emergencia", aloc=0)
        _reg(c, f, "2026-01", 300000)
        c.commit()
    finally:
        c.close()

    r = cliente.post("/configuracao/despesa-mensal", data={"despesa_mensal": "1.500,00"})

    assert r.status_code == 200
    assert "2,0 meses" in r.text
    c = db.connect()
    try:
        assert configuracao.obter_despesa_mensal(c) == 150000
    finally:
        c.close()
    assert any(copias.iterdir())  # a alteração entra numa cópia de segurança


def test_despesa_invalida_nao_grava_e_mantem_o_texto(cliente):
    c = db.connect()
    try:
        f = _plat(c, "Fundo Exemplo", categoria="emergencia", aloc=0)
        _reg(c, f, "2026-01", 300000)
        c.commit()
    finally:
        c.close()

    r = cliente.post("/configuracao/despesa-mensal", data={"despesa_mensal": "0"})

    assert r.status_code == 422
    assert "maior que zero" in r.text
    assert 'value="0"' in r.text
    c = db.connect()
    try:
        assert configuracao.obter_despesa_mensal(c) is None
    finally:
        c.close()


def test_despesa_em_branco_apaga_a_referencia(cliente):
    c = db.connect()
    try:
        f = _plat(c, "Fundo Exemplo", categoria="emergencia", aloc=0)
        _reg(c, f, "2026-01", 300000)
        c.commit()
        configuracao.definir_despesa_mensal(c, 150000)
    finally:
        c.close()
    r = cliente.post("/configuracao/despesa-mensal", data={"despesa_mensal": ""})
    assert r.status_code == 200
    assert "Define a despesa mensal de referência" in r.text


def test_despesa_de_outra_origem_e_recusada(cliente):
    r = cliente.post("/configuracao/despesa-mensal", data={"despesa_mensal": "1500"},
                     headers={"origin": "https://atacante.example"})
    assert r.status_code == 403
