from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import checkin, dashboard, db, plataformas, planos
from app.main import app

HOJE = date(2026, 11, 5)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _form(**extra):
    base = {"nome": "Corretora", "categoria": "investimento", "titular": "Ana", "plano_mensal": "50,00",
            "calcula_ganho": "1", "entra_alocacao": "1", "ordem": "3"}
    base.update(extra)
    return {k: v for k, v in base.items() if v is not None}


def _criar(conn, **extra):
    v = plataformas.validar(_form(**extra))
    assert v.ok, v.erros
    return plataformas.criar(conn, v.dados)


def _reg(conn, pid, mes, saldo, aporte=0):
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, ?, ?, ?)",
        (pid, mes, saldo, aporte),
    )
    conn.commit()


def _registo(conn, pid, mes):
    return conn.execute(
        "SELECT saldo_cent, aporte_cent FROM registos_mensais WHERE plataforma_id = ? AND mes = ?", (pid, mes)
    ).fetchone()


# --- validação ----------------------------------------------------------------

def test_validar_converte_os_campos():
    v = plataformas.validar(_form(finalidade="  Fundo  "))
    assert v.ok
    d = v.dados
    assert (d.nome, d.categoria, d.titular, d.finalidade) == ("Corretora", "investimento", "Ana", "Fundo")
    assert d.plano_mensal_cent == 5000 and d.ordem == 3
    assert d.calcula_ganho and d.entra_alocacao and d.desafio_inicio is None


def test_checkboxes_ausentes_ficam_desligadas():
    d = plataformas.validar(_form(calcula_ganho=None, entra_alocacao=None)).dados
    assert not d.calcula_ganho and not d.entra_alocacao


@pytest.mark.parametrize("campo, valor", [
    ("nome", "  "), ("titular", ""), ("categoria", "acoes"), ("plano_mensal", "1.234.56"),
    ("plano_mensal", "-5"), ("ordem", "um"),
])
def test_validar_rejeita(campo, valor):
    v = plataformas.validar(_form(**{campo: valor}))
    assert not v.ok and campo in v.erros


def test_desafio_exige_data_de_inicio():
    assert "desafio_inicio" in plataformas.validar(_form(desafio="1", desafio_inicio="")).erros
    assert plataformas.validar(_form(desafio="1", desafio_inicio="2024-01-01")).dados.desafio_inicio == date(2024, 1, 1)


# --- criar e editar -------------------------------------------------------------

def test_criar_e_aparece_no_checkin(conn):
    pid = _criar(conn)
    assert [l.plataforma_id for l in checkin.linhas_checkin(conn, "2026-11")] == [pid]


def test_nome_repetido_e_recusado_sem_distinguir_maiusculas(conn):
    _criar(conn)
    with pytest.raises(ValueError):
        _criar(conn, nome="corretora")


def test_criar_com_desafio_grava_o_plano(conn):
    pid = _criar(conn, desafio="1", desafio_inicio="2024-01-01")
    assert conn.execute("SELECT tipo, data_inicio FROM planos WHERE plataforma_id = ?", (pid,)).fetchone()[:] == (
        planos.TIPO_DESAFIO_52, "2024-01-01")


def test_atualizar_muda_dados_e_tira_o_desafio(conn):
    pid = _criar(conn, desafio="1", desafio_inicio="2024-01-01")
    v = plataformas.validar(_form(nome="Corretora B", plano_mensal="75"))
    plataformas.atualizar(conn, pid, v.dados)
    p = plataformas.obter(conn, pid)
    assert (p["nome"], p["plano_mensal_cent"], p["desafio_inicio"]) == ("Corretora B", 7500, None)


def test_atualizar_mantem_o_proprio_nome(conn):
    pid = _criar(conn)
    plataformas.atualizar(conn, pid, plataformas.validar(_form(titular="Rui")).dados)
    assert plataformas.obter(conn, pid)["titular"] == "Rui"


def test_atualizar_para_nome_de_outra_e_recusado(conn):
    _criar(conn, nome="A")
    b = _criar(conn, nome="B")
    with pytest.raises(ValueError):
        plataformas.atualizar(conn, b, plataformas.validar(_form(nome="A")).dados)


def test_proxima_ordem(conn):
    assert plataformas.proxima_ordem(conn) == 1
    _criar(conn, ordem="7")
    assert plataformas.proxima_ordem(conn) == 8


# --- desativar, fechar, reativar, apagar ----------------------------------------

def test_desativar_nao_grava_registo_e_sai_do_checkin(conn):
    pid = _criar(conn)
    _reg(conn, pid, "2026-10", 50000)
    _reg(conn, pid, "2026-11", 0, aporte=-50000)
    plataformas.desativar(conn, pid)
    assert _registo(conn, pid, "2026-12") is None
    assert checkin.linhas_checkin(conn, "2026-12") == []
    assert plataformas.ultimo_saldo(conn, pid)[:] == ("2026-11", 0)


def test_desativar_com_saldo_e_recusado(conn):
    pid = _criar(conn)
    _reg(conn, pid, "2026-10", 50000)
    with pytest.raises(ValueError, match="saldo 0"):
        plataformas.desativar(conn, pid)
    assert plataformas.obter(conn, pid)["ativa"] == 1


def test_desativar_conta_o_ultimo_registo_e_nao_um_zero_antigo(conn):
    pid = _criar(conn)
    _reg(conn, pid, "2026-09", 0)
    _reg(conn, pid, "2026-10", 100)
    with pytest.raises(ValueError):
        plataformas.desativar(conn, pid)


def test_desativar_sem_registos_e_permitido(conn):
    pid = _criar(conn)
    plataformas.desativar(conn, pid)
    assert plataformas.obter(conn, pid)["ativa"] == 0


def test_desativar_duas_vezes_falha(conn):
    pid = _criar(conn)
    plataformas.desativar(conn, pid)
    with pytest.raises(LookupError):
        plataformas.desativar(conn, pid)


def test_conta_fechada_passa_para_o_destino_sem_perda_falsa(conn):
    """Z tinha 500 € em outubro e foi fechada; no check-in de novembro fica a 0 e o dinheiro está na A."""
    a = _criar(conn, nome="A")
    z = _criar(conn, nome="Z")
    _reg(conn, a, "2026-10", 100000)
    _reg(conn, z, "2026-10", 50000)
    _reg(conn, a, "2026-11", 150200, aporte=50000)  # recebeu os 500 € e ganhou 2 €
    _reg(conn, z, "2026-11", 0, aporte=-50000)  # levantamento
    plataformas.desativar(conn, z)
    painel = dashboard.construir_painel(conn, HOJE)
    assert painel.totais.patrimonio_cent == 150200
    assert painel.totais.variacao_cent == 200
    assert painel.totais.ganho_cent == 200  # sem perda falsa na Z
    aportes = conn.execute("SELECT SUM(aporte_cent) FROM registos_mensais WHERE mes = '2026-11'").fetchone()[0]
    assert aportes == 0  # a transferência não conta como poupança nova
    assert [c.nome for c in painel.cartoes] == ["A"]
    investimento = next(s for s in painel.evolucao if s.categoria == "investimento")
    assert investimento.valores_cent == (150000, 150200)  # o passado não muda


def test_inativa_nao_volta_a_contar_nos_meses_seguintes(conn):
    a = _criar(conn, nome="A")
    z = _criar(conn, nome="Z")
    _reg(conn, z, "2026-09", 30000)
    _reg(conn, z, "2026-10", 0, aporte=-30000)
    _reg(conn, a, "2026-10", 30000, aporte=30000)
    _reg(conn, a, "2026-11", 30100)
    plataformas.desativar(conn, z)
    painel = dashboard.construir_painel(conn, HOJE)
    investimento = next(s for s in painel.evolucao if s.categoria == "investimento")
    assert investimento.valores_cent == (30000, 30000, 30100)


def test_reativar(conn):
    pid = _criar(conn)
    plataformas.desativar(conn, pid)
    plataformas.reativar(conn, pid)
    assert plataformas.obter(conn, pid)["ativa"] == 1


def test_apagar_so_sem_registos(conn):
    pid = _criar(conn)
    _reg(conn, pid, "2026-10", 100)
    with pytest.raises(ValueError):
        plataformas.apagar(conn, pid)
    outra = _criar(conn, nome="Outra", desafio="1", desafio_inicio="2024-01-01")
    plataformas.apagar(conn, outra)
    assert plataformas.obter(conn, outra) is None
    assert conn.execute("SELECT COUNT(*) FROM planos").fetchone()[0] == 0


def test_listar_ativas_primeiro_com_contagens(conn):
    a = _criar(conn, nome="A", ordem="1")
    b = _criar(conn, nome="B", ordem="2")
    _reg(conn, b, "2026-09", 1)
    _reg(conn, b, "2026-10", 1)
    plataformas.desativar(conn, a)
    lista = plataformas.listar(conn)
    assert [(p["nome"], p["n_registos"], p["ultimo_mes"]) for p in lista] == [("B", 2, "2026-10"), ("A", 0, None)]


# --- rotas ----------------------------------------------------------------------

@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as c:
        yield c


def test_ecra_lista_e_cria(cliente):
    assert cliente.get("/plataformas").status_code == 200
    r = cliente.post("/plataformas", data=_form())
    assert r.status_code == 200 and "criada" in r.text
    assert "Corretora" in cliente.get("/plataformas").text


def test_ecra_erro_mantem_o_que_foi_escrito(cliente):
    r = cliente.post("/plataformas", data=_form(titular="", nome="Nova"))
    assert r.status_code == 422
    assert 'value="Nova"' in r.text and "Indica o titular" in r.text


def test_ecra_editar_desativar_e_reativar(cliente):
    cliente.post("/plataformas", data=_form())
    pid = db.connect().execute("SELECT id FROM plataformas").fetchone()[0]
    assert "Editar Corretora" in cliente.get(f"/plataformas/{pid}").text
    assert "atualizada" in cliente.post(f"/plataformas/{pid}", data=_form(nome="Corretora X")).text
    assert "desativada" in cliente.post(f"/plataformas/{pid}/desativar").text  # sem registos
    assert "reativada" in cliente.post(f"/plataformas/{pid}/reativar").text


def test_ecra_desativar_com_saldo_mostra_o_caminho(cliente):
    cliente.post("/plataformas", data=_form())
    c = db.connect()
    pid = c.execute("SELECT id FROM plataformas").fetchone()[0]
    _reg(c, pid, "2026-10", 50000)
    assert "disabled" in cliente.get(f"/plataformas/{pid}").text
    r = cliente.post(f"/plataformas/{pid}/desativar")
    assert r.status_code == 422 and "aporte negativo" in r.text
    assert c.execute("SELECT ativa FROM plataformas").fetchone()[0] == 1


def test_ecra_plataforma_inexistente(cliente):
    assert cliente.get("/plataformas/999").status_code == 404
    assert cliente.post("/plataformas/999/apagar").status_code == 404


def test_ecra_acao_desconhecida(cliente):
    cliente.post("/plataformas", data=_form())
    pid = db.connect().execute("SELECT id FROM plataformas").fetchone()[0]
    assert cliente.post(f"/plataformas/{pid}/explodir").status_code == 404


def test_alteracao_faz_copia_de_seguranca(cliente, monkeypatch, tmp_path):
    from app import backup

    cliente.post("/plataformas", data=_form())
    assert backup.listar_copias(backup.pasta_backup_por_defeito())


def test_ecra_recusa_post_de_outra_origem(cliente):
    r = cliente.post("/plataformas", data=_form(), headers={"origin": "https://atacante.example"})
    assert r.status_code == 403
