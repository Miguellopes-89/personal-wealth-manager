"""Ecrã /aforro e secção do painel (v7). Valores fictícios."""

import pytest
from fastapi.testclient import TestClient

from app import aforro, db
from app.main import app

FORM = {"plataforma_id": "1", "serie": "E", "data_subscricao": "2023-01-10", "unidades": "1000",
        "valor_unitario": "1,05123", "data_valor": "2026-01-15"}


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    monkeypatch.setenv("PWM_BACKUP", str(tmp_path / "backup"))
    with TestClient(app) as c:
        conn = db.connect()
        conn.execute("INSERT INTO plataformas (id, nome, categoria, titular) VALUES (1, 'Certificados de Aforro Exemplo', 'poupanca', 'Ana')")
        conn.execute("INSERT INTO plataformas (id, nome, categoria, titular) VALUES (2, 'Outra', 'poupanca', 'Rui')")
        conn.execute("INSERT INTO registos_mensais VALUES (1, '2026-01', 105123, 0, '2026-01-15')")
        conn.commit()
        conn.close()
        yield c


def _lista():
    conn = db.connect()
    try:
        return aforro.listar(conn)
    finally:
        conn.close()


def test_barra_lateral_e_ecra_vazio(cliente):
    r = cliente.get("/aforro")
    assert r.status_code == 200 and 'href="/aforro"' in r.text and "Ainda não há subscrições" in r.text
    assert 'value="1" selected' in r.text  # escolhe por defeito a plataforma com "aforro" no nome
    assert "Certificados de Aforro</h2>" not in cliente.get("/").text  # painel sem subscrições: sem secção


def test_criar_mostra_simulacao_no_ecra_e_no_painel(cliente):
    r = cliente.post("/aforro", data=FORM)
    assert r.status_code == 200 and "Subscrição acrescentada" in r.text
    assert "1.051,23 €" in r.text and "10/01/2033" in r.text and "Sem taxa base atual" in r.text
    assert len(_lista()) == 1

    r = cliente.post("/aforro/taxa", data={"taxa": "2,5"})
    assert "Taxa base de 2,5 % guardada" in r.text and "taxa base atual" in r.text and "Sem taxa base" not in r.text

    painel = cliente.get("/").text
    assert "Certificados de Aforro</h2>" in painel and "10/01/2033" in painel and "(2,5 %)" in painel


def test_erros_nao_gravam_e_mantem_o_texto(cliente):
    r = cliente.post("/aforro", data={**FORM, "valor_unitario": "0,9", "unidades": "abc"})
    assert r.status_code == 422 and 'value="0,9"' in r.text and "capital é garantido" in r.text
    assert "data-por-gravar" in r.text and _lista() == []
    r = cliente.post("/aforro/taxa", data={"taxa": "4"})
    assert r.status_code == 422 and 'value="4"' in r.text


def test_editar_e_apagar(cliente):
    cliente.post("/aforro", data=FORM)
    sid = _lista()[0].id
    r = cliente.get(f"/aforro/{sid}")
    assert "Editar subscrição de 10/01/2023" in r.text and 'value="1,05123"' in r.text
    r = cliente.post(f"/aforro/{sid}", data={**FORM, "valor_unitario": "1,06", "data_valor": "2026-04-15"})
    assert "Subscrição atualizada" in r.text and _lista()[0].valor_unitario == 106000
    r = cliente.post(f"/aforro/{sid}/apagar")
    assert "Subscrição apagada" in r.text and _lista() == []
    assert cliente.get("/aforro/999").status_code == 404


def test_backup_inclui_subscricoes(cliente, tmp_path):
    cliente.post("/aforro", data=FORM)
    copias = sorted((tmp_path / "backup").iterdir())
    assert (copias[-1] / "subscricoes_aforro.csv").read_text(encoding="utf-8-sig").count("\n") == 2
