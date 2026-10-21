"""Posição das plataformas escolhida numa lista (sessão 14).

A lista mostra as plataformas ativas da mesma categoria; a coluna `ordem` continua global (check-in e
tabela) e é renumerada 10, 20, 30… sem mudar a ordem relativa das outras. Valores fictícios.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app import checkin, db, plataformas
from app.main import app


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _form(nome, categoria="investimento", posicao="", **extra):
    base = {"nome": nome, "categoria": categoria, "titular": "Ana", "plano_mensal": "0",
            "calcula_ganho": "1", "entra_alocacao": "1", "posicao": posicao}
    base.update(extra)
    return base


def _criar(conn, nome, categoria="investimento", posicao=""):
    v = plataformas.validar(_form(nome, categoria, posicao))
    assert v.ok, v.erros
    return plataformas.criar(conn, v.dados)


def _atualizar(conn, pid, nome, categoria="investimento", posicao=None, **extra):
    if posicao is None:
        posicao = plataformas.posicao_atual(conn, pid)
    v = plataformas.validar(_form(nome, categoria, posicao, **extra))
    assert v.ok, v.erros
    plataformas.atualizar(conn, pid, v.dados)


def _nomes(conn):
    return [r["nome"] for r in conn.execute("SELECT nome FROM plataformas ORDER BY ordem, id")]


def _ordens(conn):
    return [r[0] for r in conn.execute("SELECT ordem FROM plataformas ORDER BY ordem, id")]


@pytest.fixture
def base(conn):
    """Ordem global: I1, P1, I2, V1 (investimento e p2p intercalados de propósito)."""
    ids = {
        "I1": _criar(conn, "I1"),
        "P1": _criar(conn, "P1", "p2p"),
    }
    ids["I2"] = _criar(conn, "I2")  # no fim da categoria investimento = logo a seguir a I1
    ids["V1"] = _criar(conn, "V1", "viagens")
    # Repor o intercalado: I2 depois de P1 (pôr à mão, como numa base antiga)
    conn.execute("UPDATE plataformas SET ordem = CASE nome WHEN 'I1' THEN 1 WHEN 'P1' THEN 2 WHEN 'I2' THEN 3 ELSE 4 END")
    conn.commit()
    assert _nomes(conn) == ["I1", "P1", "I2", "V1"]
    return ids


# --- criar ----------------------------------------------------------------------

def test_criar_sem_posicao_fica_no_fim_da_categoria_e_renumera(conn, base):
    _criar(conn, "I3")
    assert _nomes(conn) == ["I1", "P1", "I2", "I3", "V1"]
    assert _ordens(conn) == [10, 20, 30, 40, 50]


def test_criar_no_inicio_da_categoria(conn, base):
    _criar(conn, "I0", posicao="inicio")
    assert _nomes(conn) == ["I0", "I1", "P1", "I2", "V1"]


def test_criar_depois_de_uma_plataforma(conn, base):
    _criar(conn, "Ix", posicao=f"depois:{base['I1']}")
    assert _nomes(conn) == ["I1", "Ix", "P1", "I2", "V1"]


def test_criar_numa_categoria_sem_plataformas_vai_para_o_fim(conn, base):
    _criar(conn, "R1", "reforma", posicao="inicio")
    assert _nomes(conn) == ["I1", "P1", "I2", "V1", "R1"]


def test_primeira_plataforma_de_todas(conn):
    _criar(conn, "Unica")
    assert _ordens(conn) == [10]


# --- editar ---------------------------------------------------------------------

def test_editar_sem_mexer_na_posicao_nao_sai_do_sitio(conn, base):
    """I2 está depois de P1 (outra categoria); gravar com a posição que já tem não a junta a I1."""
    assert plataformas.posicao_atual(conn, base["I2"]) == f"depois:{base['I1']}"
    _atualizar(conn, base["I2"], "I2", titular="Rui")
    assert _nomes(conn) == ["I1", "P1", "I2", "V1"]
    assert plataformas.obter(conn, base["I2"])["titular"] == "Rui"


def test_editar_para_o_inicio(conn, base):
    _atualizar(conn, base["I2"], "I2", posicao="inicio")
    assert _nomes(conn) == ["I2", "I1", "P1", "V1"]
    assert _ordens(conn) == [10, 20, 30, 40]


def test_editar_para_o_fim_mantem_as_outras_na_ordem_relativa(conn, base):
    _atualizar(conn, base["I1"], "I1", posicao="")
    assert _nomes(conn) == ["P1", "I2", "I1", "V1"]


def test_mudar_de_categoria_vai_para_o_fim_da_nova(conn, base):
    _atualizar(conn, base["V1"], "V1", "investimento", posicao="")
    assert _nomes(conn) == ["I1", "P1", "I2", "V1"]
    _atualizar(conn, base["I1"], "I1", "p2p", posicao="")
    assert _nomes(conn) == ["P1", "I1", "I2", "V1"]


def test_mudar_para_categoria_vazia_fica_onde_estava(conn, base):
    _atualizar(conn, base["P1"], "P1", "reforma", posicao="")
    assert _nomes(conn) == ["I1", "P1", "I2", "V1"]


# --- posições recusadas ----------------------------------------------------------

@pytest.mark.parametrize("quem", ["P1", "I2-propria", "inexistente"])
def test_posicao_que_nao_serve_e_recusada_e_nada_fica_gravado(conn, base, quem):
    alvo = {"P1": base["P1"], "I2-propria": base["I2"], "inexistente": 999}[quem]
    v = plataformas.validar(_form("I2 novo nome", posicao=f"depois:{alvo}"))
    with pytest.raises(plataformas.PosicaoInvalida):
        plataformas.atualizar(conn, base["I2"], v.dados)
    assert _nomes(conn) == ["I1", "P1", "I2", "V1"]
    assert plataformas.obter(conn, base["I2"])["nome"] == "I2"
    if quem != "I2-propria":  # numa plataforma nova, "depois de I2" é válido
        with pytest.raises(plataformas.PosicaoInvalida):
            plataformas.criar(conn, plataformas.validar(_form("Nova", posicao=f"depois:{alvo}")).dados)
        assert conn.execute("SELECT COUNT(*) FROM plataformas").fetchone()[0] == 4


def test_depois_de_uma_inativa_e_recusado(conn, base):
    plataformas.desativar(conn, base["I1"])
    with pytest.raises(plataformas.PosicaoInvalida):
        _criar(conn, "Nova", posicao=f"depois:{base['I1']}")


# --- lista e posição atual -------------------------------------------------------

def test_inativas_ficam_fora_da_lista(conn, base):
    plataformas.desativar(conn, base["I1"])
    assert [o["nome"] for o in plataformas.opcoes_posicao(conn)] == ["P1", "I2", "V1"]


def test_posicao_atual(conn, base):
    assert plataformas.posicao_atual(conn, base["I1"]) == "inicio"
    assert plataformas.posicao_atual(conn, base["P1"]) == ""  # única ativa da categoria
    plataformas.desativar(conn, base["I1"])
    assert plataformas.posicao_atual(conn, base["I2"]) == ""  # a outra ficou inativa


def test_editar_uma_inativa_sem_mexer_na_posicao_nao_a_move(conn, base):
    plataformas.desativar(conn, base["I1"])
    _atualizar(conn, base["I1"], "I1", titular="Rui")
    assert _nomes(conn) == ["I1", "P1", "I2", "V1"]


def test_check_in_segue_a_nova_ordem(conn, base):
    _atualizar(conn, base["V1"], "V1", "viagens", posicao="")
    _atualizar(conn, base["I2"], "I2", posicao="inicio")
    assert [l.nome for l in checkin.linhas_checkin(conn, "2026-11")] == ["I2", "I1", "P1", "V1"]


# --- ecrã -----------------------------------------------------------------------

@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as c:
        yield c


def _ids_no_ecra(cliente):
    return [int(i) for i in re.findall(r'href="/plataformas/(\d+)#formulario"', cliente.get("/plataformas").text)]


def test_ecra_edicao_mostra_a_posicao_atual_e_esconde_a_propria(cliente):
    for nome in ("I1", "I2"):
        assert cliente.post("/plataformas", data=_form(nome)).status_code == 200
    i1, i2 = _ids_no_ecra(cliente)
    html = cliente.get(f"/plataformas/{i2}").text
    assert f'<option value="depois:{i1}" data-categoria="investimento" selected>Depois de I1</option>' in html
    assert f'value="depois:{i2}"' not in html
    assert 'name="ordem"' not in html


def test_ecra_nova_plataforma_comeca_no_fim(cliente):
    html = cliente.get("/plataformas").text
    assert '<option value="" selected>No fim da categoria</option>' in html


def test_ecra_move_e_a_tabela_mostra_a_nova_ordem(cliente):
    for nome in ("I1", "I2"):
        cliente.post("/plataformas", data=_form(nome))
    i1, i2 = _ids_no_ecra(cliente)
    r = cliente.post(f"/plataformas/{i2}", data=_form("I2", posicao="inicio"))
    assert r.status_code == 200 and "atualizada" in r.text
    assert _ids_no_ecra(cliente) == [i2, i1]


def test_ecra_posicao_de_outra_categoria_da_erro_no_campo(cliente):
    cliente.post("/plataformas", data=_form("I1"))
    cliente.post("/plataformas", data=_form("P1", "p2p"))
    i1, p1 = _ids_no_ecra(cliente)
    r = cliente.post(f"/plataformas/{i1}", data=_form("I1 mudado", posicao=f"depois:{p1}"))
    assert r.status_code == 422
    assert "Nada foi gravado" in r.text and "não é uma plataforma ativa desta categoria" in r.text
    assert 'id="campo-posicao" class="erro"' in r.text
    assert "I1 mudado" not in cliente.get("/plataformas").text.split('id="formulario"')[0]
