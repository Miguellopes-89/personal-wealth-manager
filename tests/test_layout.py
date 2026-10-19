"""Estrutura comum dos ecrãs: barra lateral, estilo e tipo de letra locais (a aplicação é offline)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

PAGINAS = ["/", "/checkin", "/plataformas"]


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "pwm.db"))
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


@pytest.mark.parametrize("caminho", PAGINAS)
def test_todas_as_paginas_usam_a_barra_lateral_e_nada_externo(cliente, caminho):
    r = cliente.get(caminho)
    assert r.status_code == 200
    assert '<link rel="stylesheet" href="/static/css/pwm.css">' in r.text
    assert r.text.count('id="form-sair"') == 1  # um só "Guardar e sair", na barra lateral
    assert "https://" not in r.text and "http://" not in r.text


@pytest.mark.parametrize("caminho,ativo", [("/", 'href="/" aria-current'), ("/checkin", 'href="/checkin" aria-current'),
                                           ("/plataformas", 'href="/plataformas" aria-current')])
def test_navegacao_marca_a_pagina_atual(cliente, caminho, ativo):
    r = cliente.get(caminho)
    assert ativo in r.text and r.text.count("aria-current") == 1


def test_estilo_e_fontes_sao_servidos_localmente(cliente):
    css = cliente.get("/static/css/pwm.css")
    assert css.status_code == 200 and "http" not in css.text
    for peso in (400, 500, 600):
        f = cliente.get(f"/static/vendor/fonts/ibm-plex-sans-latin-{peso}-normal.woff2")
        assert f.status_code == 200 and f.content[:4] == b"wOF2"
    assert cliente.get("/static/vendor/fonts/OFL-IBM-Plex-Sans.txt").status_code == 200
