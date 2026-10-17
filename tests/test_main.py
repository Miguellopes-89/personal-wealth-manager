from fastapi.testclient import TestClient

from app.main import app


def test_pagina_inicial_responde(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as cliente:  # o "with" corre o arranque (cria as tabelas)
        resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "Personal Wealth Manager" in resposta.text
    assert "Plataformas na base de dados: 0" in resposta.text
