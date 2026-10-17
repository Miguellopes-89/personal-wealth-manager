import pytest
from fastapi.testclient import TestClient

from app import backup, main
from app.main import app


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    monkeypatch.setenv("PWM_BACKUP", str(tmp_path / "backup"))
    chamadas = []
    # Nos testes nunca se envia o sinal a sério: só se regista que foi pedido.
    monkeypatch.setattr(main, "desligar", lambda: chamadas.append(1))
    with TestClient(app) as c:
        c.chamadas = chamadas
        yield c


def test_sair_faz_copia_e_pede_para_desligar(cliente, tmp_path):
    r = cliente.post("/sair")
    assert r.status_code == 200
    assert "Guardado" in r.text
    copias = list((tmp_path / "backup").iterdir())
    assert len(copias) == 1
    assert (copias[0] / "plataformas.csv").is_file()
    assert cliente.chamadas == [1]


def test_se_a_copia_falhar_a_app_fica_aberta(cliente, monkeypatch):
    def falha(*_a, **_k):
        raise OSError("disco cheio")

    monkeypatch.setattr(backup, "exportar_csv", falha)
    r = cliente.post("/sair")
    assert r.status_code == 500
    assert "disco cheio" in r.text
    assert "continua aberta" in r.text
    assert cliente.chamadas == []  # não desligou


def test_sair_nao_responde_a_get(cliente):
    assert cliente.get("/sair").status_code == 405
    assert cliente.chamadas == []


def test_botao_existe_na_pagina_inicial_e_no_checkin(cliente):
    assert "/sair" in cliente.get("/").text
    assert 'action="/sair"' in cliente.get("/checkin?mes=2026-01").text
