import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_pagina_inicial_responde(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as cliente:  # o "with" corre o arranque (cria as tabelas)
        resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "Personal Wealth Manager" in resposta.text
    assert "Ainda não há registos" in resposta.text


def _cliente(monkeypatch, tmp_path, base_url="http://127.0.0.1:8000"):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    return TestClient(app, base_url=base_url)


def test_host_alheio_e_recusado(monkeypatch, tmp_path):
    """DNS rebinding: um domínio externo a apontar para 127.0.0.1 chega com o seu próprio Host."""
    with _cliente(monkeypatch, tmp_path, base_url="http://atacante.example") as c:
        assert c.get("/").status_code == 400


def test_localhost_e_aceite(monkeypatch, tmp_path):
    for base in ("http://127.0.0.1:8000", "http://localhost:8000"):
        with _cliente(monkeypatch, tmp_path, base_url=base) as c:
            assert c.get("/").status_code == 200


@pytest.mark.parametrize("cabecalho", [
    {"origin": "https://atacante.example"},
    {"origin": "null"},
    {"referer": "https://atacante.example/pagina"},
    {"origin": "http://127.0.0.1:9999"},  # outra porta = outra origem
])
def test_post_de_outra_origem_e_recusado(monkeypatch, tmp_path, cabecalho):
    with _cliente(monkeypatch, tmp_path) as c:
        assert c.post("/checkin", data={"mes": "2026-01"}, headers=cabecalho).status_code == 403
        assert c.post("/sair", headers=cabecalho).status_code == 403


def test_post_da_propria_app_passa(monkeypatch, tmp_path):
    with _cliente(monkeypatch, tmp_path) as c:
        r = c.post("/checkin", data={"mes": "2026-01"}, headers={"origin": "http://127.0.0.1:8000"})
    assert r.status_code == 200
