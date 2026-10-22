"""Ecrãs dos índices (v6): página /indices e campos no check-in. Valores fictícios."""
import pytest
from fastapi.testclient import TestClient

from app import db, indices
from app.main import app

MES = "2026-01"  # passado em qualquer data de execução realista


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as c:
        yield c


def _com_conn(f):
    conn = db.connect()
    try:
        return f(conn)
    finally:
        conn.close()


def test_barra_lateral_tem_indices(cliente):
    r = cliente.get("/")
    assert 'href="/indices"' in r.text


def test_criar_editar_desativar_apagar(cliente):
    r = cliente.post("/indices", data={"nome": "Ações mundo", "perimetro": "investimento"})
    assert r.status_code == 200 and "criado" in r.text
    i = _com_conn(lambda c: indices.listar(c))[0]
    assert (i.nome, i.perimetro) == ("Ações mundo", "investimento")

    r = cliente.get(f"/indices/{i.id}")
    assert "Editar Ações mundo" in r.text and 'value="investimento" selected' in r.text

    r = cliente.post(f"/indices/{i.id}", data={"nome": "Inflação", "perimetro": ""})
    assert r.status_code == 200
    assert _com_conn(lambda c: indices.obter(c, i.id)).perimetro is None

    assert cliente.post(f"/indices/{i.id}/desativar").status_code == 200
    assert not _com_conn(lambda c: indices.obter(c, i.id)).ativo
    assert cliente.post(f"/indices/{i.id}/reativar").status_code == 200
    assert cliente.post(f"/indices/{i.id}/apagar").status_code == 200
    assert _com_conn(lambda c: indices.listar(c)) == []


def test_erro_mantem_o_que_foi_escrito(cliente):
    cliente.post("/indices", data={"nome": "Inflação", "perimetro": ""})
    r = cliente.post("/indices", data={"nome": "INFLACAO", "perimetro": "investimento"})
    assert r.status_code == 422
    assert "Já existe" in r.text and 'value="INFLACAO"' in r.text and "data-por-gravar" in r.text


def test_acoes_desconhecidas_e_inexistentes(cliente):
    assert cliente.get("/indices/99").status_code == 404
    assert cliente.post("/indices/99/apagar").status_code == 404
    cliente.post("/indices", data={"nome": "Inflação"})
    i = _com_conn(lambda c: indices.listar(c))[0]
    assert cliente.post(f"/indices/{i.id}/outra").status_code == 404
    assert cliente.post(f"/indices/{i.id}/valores/2026-01/apagar").status_code == 404


def test_apagar_com_valores_recusa_e_valor_apaga_se(cliente):
    cliente.post("/indices", data={"nome": "Inflação"})
    i = _com_conn(lambda c: indices.listar(c))[0]
    cliente.post("/checkin", data={"mes": MES, "data": "2026-01-31", f"indice_{i.id}": "118,42"})

    r = cliente.post(f"/indices/{i.id}/apagar")
    assert r.status_code == 422 and "desativa-o" in r.text
    r = cliente.get(f"/indices/{i.id}")
    assert "118,42" in r.text and "01-2026" in r.text

    assert cliente.post(f"/indices/{i.id}/valores/{MES}/apagar").status_code == 200
    assert _com_conn(lambda c: indices.valores(c, i.id)) == {}


def test_checkin_mostra_so_ativos_com_referencia_e_valor_gravado(cliente):
    cliente.post("/indices", data={"nome": "Ações mundo", "perimetro": "investimento"})
    cliente.post("/indices", data={"nome": "Velho"})
    a, velho = _com_conn(lambda c: indices.listar(c))
    cliente.post(f"/indices/{velho.id}/desativar")
    _com_conn(lambda c: (indices.gravar_valores(c, "2025-12", {a.id: 1200000}), c.commit()))

    r = cliente.get(f"/checkin?mes={MES}")
    assert f'name="indice_{a.id}"' in r.text and f'name="indice_{velho.id}"' not in r.text
    assert "120" in r.text and "12-2025" in r.text  # referência do mês anterior

    r = cliente.post("/checkin", data={"mes": MES, "data": "2026-01-31", f"indice_{a.id}": "130,145"})
    assert r.status_code == 200 and "1 valor(es) de índices" in r.text
    r = cliente.get(f"/checkin?mes={MES}")
    assert 'value="130,145"' in r.text  # pré-preenchido com o gravado


def test_checkin_com_indice_invalido_nao_grava_nada(cliente):
    conn = db.connect()
    pid = conn.execute("INSERT INTO plataformas (nome, categoria, titular) VALUES ('X', 'poupanca', 'Ana')").lastrowid
    conn.commit()
    conn.close()
    cliente.post("/indices", data={"nome": "Inflação"})
    i = _com_conn(lambda c: indices.listar(c))[0]

    r = cliente.post("/checkin", data={"mes": MES, "data": "2026-01-31", f"saldo_{pid}": "100,00",
                                       f"indice_{i.id}": "abc"})

    assert r.status_code == 422
    assert 'value="abc"' in r.text and "data-por-gravar" in r.text
    assert _com_conn(lambda c: c.execute("SELECT COUNT(*) FROM registos_mensais").fetchone()[0]) == 0
