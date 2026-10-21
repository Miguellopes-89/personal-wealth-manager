"""Aviso do "Guardar e sair" quando há valores por gravar: check-in, despesa mensal do painel e plataformas.

O pytest não corre JavaScript: estes testes confirmam que o script comum está na página, que os formulários
certos estão marcados (data-avisar-sair) e que um ecrã devolvido com erro fica marcado como "por gravar".
O comportamento no browser verifica-se à parte (Chromium).
"""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

MES = "2026-01"  # passado em qualquer data de execução realista


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    monkeypatch.setenv("PWM_BACKUP", str(tmp_path / "copias"))
    with TestClient(app) as c:
        yield c


def _plataforma(categoria="viagens"):
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO plataformas (nome, categoria, titular) VALUES ('Exemplo', ?, 'Ana')", (categoria,)
        )
        pid = cur.lastrowid
        conn.execute(
            "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent) VALUES (?, ?, 100000, 0)",
            (pid, MES),
        )
        conn.commit()
        return pid
    finally:
        conn.close()


def _form_plataforma(**extra):
    dados = {"nome": "Nova", "categoria": "viagens", "titular": "Ana", "plano_mensal": "", "ordem": ""}
    dados.update(extra)
    return dados


def _formulario(html, action):
    """Etiqueta de abertura do formulário POST com este action (o "Abrir" do check-in é GET)."""
    inicio = html.index(f'method="post" action="{action}"')
    return html[html.rindex("<form", 0, inicio):html.index(">", inicio) + 1]


@pytest.mark.parametrize("caminho", ["/", "/checkin", "/plataformas"])
def test_o_script_do_aviso_vem_depois_do_botao_e_so_uma_vez(cliente, caminho):
    _plataforma(categoria="emergencia")  # para o painel mostrar o formulário da despesa mensal
    r = cliente.get(caminho)
    assert r.status_code == 200
    # liga-se ao botão pelo id: o botão tem de existir antes de o script correr
    assert r.text.index('id="form-sair"') < r.text.index("getElementById('form-sair')")
    assert r.text.count("getElementById('form-sair')") == 1  # uma só confirmação, nunca duas seguidas
    assert r.text.count("confirm(") == 1


def test_formulario_do_checkin_esta_marcado(cliente):
    _plataforma()
    r = cliente.get(f"/checkin?mes={MES}")
    form = _formulario(r.text, "/checkin")
    assert "data-avisar-sair" in form and "data-por-gravar" not in form
    # o formulário de cima (mês e data, "Abrir") não grava nada: não entra no aviso
    topo = r.text[r.text.index('<form class="caixa topo-checkin"'):]
    assert "data-avisar-sair" not in topo[:topo.index(">") + 1]


def test_checkin_devolvido_com_erro_fica_por_gravar(cliente):
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": MES, f"saldo_{pid}": "abc", f"aporte_{pid}": "0"})
    assert r.status_code == 422
    assert "data-por-gravar" in _formulario(r.text, "/checkin")


def test_checkin_gravado_nao_fica_por_gravar(cliente):
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": MES, f"saldo_{pid}": "1100,00", f"aporte_{pid}": "0"})
    assert r.status_code == 200
    assert "data-por-gravar" not in _formulario(r.text, "/checkin")


def test_despesa_mensal_do_painel_esta_marcada(cliente):
    _plataforma(categoria="emergencia")
    form = _formulario(cliente.get("/").text, "/configuracao/despesa-mensal")
    assert "data-avisar-sair" in form and "data-por-gravar" not in form


def test_despesa_mensal_recusada_fica_por_gravar(cliente):
    _plataforma(categoria="emergencia")
    r = cliente.post("/configuracao/despesa-mensal", data={"despesa_mensal": "1.500"})
    assert r.status_code == 422
    assert "data-por-gravar" in _formulario(r.text, "/configuracao/despesa-mensal")


def test_despesa_mensal_gravada_nao_fica_por_gravar(cliente):
    _plataforma(categoria="emergencia")
    r = cliente.post("/configuracao/despesa-mensal", data={"despesa_mensal": "1500,00"})
    assert r.status_code == 200
    assert "data-por-gravar" not in _formulario(r.text, "/configuracao/despesa-mensal")


def test_formulario_de_plataforma_esta_marcado_ao_criar_e_ao_editar(cliente):
    pid = _plataforma()
    nova = _formulario(cliente.get("/plataformas").text, "/plataformas")
    editar = _formulario(cliente.get(f"/plataformas/{pid}").text, f"/plataformas/{pid}")
    for form in (nova, editar):
        assert "data-avisar-sair" in form and "data-por-gravar" not in form


def test_plataforma_recusada_fica_por_gravar(cliente):
    r = cliente.post("/plataformas", data=_form_plataforma(titular=""))
    assert r.status_code == 422
    assert "data-por-gravar" in _formulario(r.text, "/plataformas")


def test_botoes_desativar_e_apagar_nao_entram_no_aviso(cliente):
    """São ações de um clique, sem valores escritos: não há nada a perder."""
    pid = _plataforma()
    html = cliente.get(f"/plataformas/{pid}").text
    assert "data-avisar-sair" not in _formulario(html, f"/plataformas/{pid}/desativar")
