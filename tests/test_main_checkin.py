import pytest
from fastapi.testclient import TestClient

from app import calc, checkin, db
from app.main import app
from app import backup

MES = "2026-01"  # passado em qualquer data de execução realista


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as c:
        yield c


def _plataforma(nome="Revolut", plano=2000):
    conn = db.connect()
    cur = conn.execute(
        """INSERT INTO plataformas (nome, categoria, titular, plano_mensal_cent)
           VALUES (?, 'viagens', 'Miguel', ?)""",
        (nome, plano),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def _registos():
    conn = db.connect()
    try:
        return conn.execute("SELECT plataforma_id, mes, saldo_cent, aporte_cent FROM registos_mensais").fetchall()
    finally:
        conn.close()


def test_cent_para_texto():
    assert checkin.cent_para_texto(12345) == "123,45"
    assert checkin.cent_para_texto(0) == "0,00"
    assert checkin.cent_para_texto(-500) == "-5,00"
    assert checkin.cent_para_texto(123456) == "1234,56"


def test_ecra_mostra_plataformas_e_aporte_do_plano(cliente):
    _plataforma("Revolut", plano=2000)
    r = cliente.get(f"/checkin?mes={MES}")
    assert r.status_code == 200
    assert "Revolut" in r.text
    assert 'value="20,00"' in r.text  # aporte pré-preenchido pelo plano


def test_mes_invalido_devolve_400(cliente):
    r = cliente.get("/checkin?mes=2026-13")
    assert r.status_code == 400


def test_gravar_e_mostrar_resumo(cliente):
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": MES, f"saldo_{pid}": "100,00", f"aporte_{pid}": "20,00"})
    assert r.status_code == 200
    assert "Gravado" in r.text
    linhas = _registos()
    assert len(linhas) == 1
    assert (linhas[0]["saldo_cent"], linhas[0]["aporte_cent"]) == (10000, 2000)


def test_erro_nao_grava_e_conserva_o_que_foi_escrito(cliente):
    a = _plataforma("A")
    b = _plataforma("B")
    r = cliente.post(
        "/checkin",
        data={"mes": MES, f"saldo_{a}": "50,00", f"aporte_{a}": "0", f"saldo_{b}": "abc", f"aporte_{b}": "0"},
    )
    assert r.status_code == 422
    assert "Nada foi gravado" in r.text
    assert 'value="50,00"' in r.text  # a linha válida não se perdeu
    assert _registos() == []


def test_mes_futuro_no_post_devolve_400(cliente):
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": "2999-01", f"saldo_{pid}": "100,00", f"aporte_{pid}": "0"})
    assert r.status_code == 400
    assert _registos() == []


def _copias_de_seguranca():
    return list(backup.pasta_backup_por_defeito().iterdir())


def test_gravar_faz_copia_de_seguranca(cliente):
    pid = _plataforma()
    assert _copias_de_seguranca() == []
    cliente.post("/checkin", data={"mes": MES, f"saldo_{pid}": "100,00", f"aporte_{pid}": "20,00"})
    copias = _copias_de_seguranca()
    assert len(copias) == 1
    assert "Revolut" in (copias[0] / "plataformas.csv").read_text(encoding="utf-8-sig")


def test_erro_de_validacao_nao_faz_copia(cliente):
    pid = _plataforma()
    cliente.post("/checkin", data={"mes": MES, f"saldo_{pid}": "abc", f"aporte_{pid}": "0"})
    assert _copias_de_seguranca() == []


def test_falha_da_copia_nao_desfaz_a_gravacao_e_avisa(cliente, monkeypatch):
    def falha(*_a, **_k):
        raise OSError("disco cheio")

    monkeypatch.setattr(backup, "exportar_csv", falha)
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": MES, f"saldo_{pid}": "100,00", f"aporte_{pid}": "20,00"})
    assert r.status_code == 200
    assert "disco cheio" in r.text
    assert len(_registos()) == 1


def test_resumo_mostra_o_total_de_aportes(cliente):
    a = _plataforma("A")
    b = _plataforma("B")
    r = cliente.post(
        "/checkin",
        data={
            "mes": MES,
            f"saldo_{a}": "100,00", f"aporte_{a}": "20,00",
            f"saldo_{b}": "50,00", f"aporte_{b}": "50,00",
        },
    )
    assert r.status_code == 200
    assert "Aportes gravados" in r.text
    assert calc.formatar_euros(7000) in r.text  # 20 + 50
