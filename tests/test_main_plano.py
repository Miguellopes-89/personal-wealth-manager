import pytest
from fastapi.testclient import TestClient

from app import db, planos
from app.main import app

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


def _bondora_com_leitura_anterior():
    """Bondora com o desafio e uma leitura a 31/12/2025; o ecrã de janeiro sugere os domingos de janeiro."""
    conn = db.connect()
    cur = conn.execute(
        "INSERT INTO plataformas (nome, categoria, titular, calcula_ganho) VALUES ('Bondora Go & Grow', 'p2p', 'Miguel', 1)"
    )
    pid = cur.lastrowid
    conn.execute(
        "INSERT INTO planos (plataforma_id, tipo, data_inicio) VALUES (?, ?, '2024-01-01')",
        (pid, planos.TIPO_DESAFIO_52),
    )
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) "
        "VALUES (?, '2025-12', 100000, 0, '2025-12-31')",
        (pid,),
    )
    conn.commit()
    conn.close()
    return pid


def _datas():
    conn = db.connect()
    try:
        return [r[0] for r in conn.execute("SELECT data_leitura FROM registos_mensais ORDER BY plataforma_id, mes")]
    finally:
        conn.close()


def test_ecra_mostra_a_data_da_leitura_por_defeito(cliente):
    _plataforma()
    r = cliente.get(f"/checkin?mes={MES}")
    assert r.status_code == 200
    assert 'value="2026-01-31"' in r.text  # mês passado: último dia do mês
    assert r.text.count('name="data"') == 2  # campo do "Abrir" e o escondido do formulário de gravação


def test_ecra_aceita_uma_data_do_mes(cliente):
    _plataforma()
    r = cliente.get(f"/checkin?mes={MES}&data=2026-01-15")
    assert 'value="2026-01-15"' in r.text


def test_ecra_com_data_de_outro_mes_volta_a_defeito_sem_erro(cliente):
    _plataforma()
    r = cliente.get(f"/checkin?mes={MES}&data=2026-02-10")  # ex.: o mês mudou e a data ficou antiga
    assert r.status_code == 200
    assert 'value="2026-01-31"' in r.text


def test_ecra_sugere_o_aporte_do_desafio_e_mostra_as_semanas(cliente):
    _bondora_com_leitura_anterior()
    r = cliente.get(f"/checkin?mes={MES}")  # domingos de janeiro de 2026: 4, 11, 18 e 25 -> 1+2+3+4 = 10 €
    assert r.status_code == 200
    assert 'value="10,00"' in r.text
    assert "sem. 4" in r.text


def test_ecra_avisa_do_domingo_do_dia_da_leitura(cliente):
    _bondora_com_leitura_anterior()
    r = cliente.get(f"/checkin?mes={MES}&data=2026-01-25")  # 25/01 é domingo
    assert "dia da leitura" in r.text
    assert 'value="10,00"' in r.text  # inclui o domingo 25/01 (semana 4)


def test_gravar_guarda_a_data_indicada(cliente):
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": MES, "data": "2026-01-15", f"saldo_{pid}": "100,00", f"aporte_{pid}": "0"})
    assert r.status_code == 200
    assert _datas() == ["2026-01-15"]


def test_gravar_sem_data_usa_a_de_defeito(cliente):
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": MES, f"saldo_{pid}": "100,00", f"aporte_{pid}": "0"})
    assert r.status_code == 200
    assert _datas() == ["2026-01-31"]


def test_data_fora_do_mes_devolve_400_e_nao_grava(cliente):
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": MES, "data": "2026-02-10", f"saldo_{pid}": "100,00", f"aporte_{pid}": "0"})
    assert r.status_code == 400
    assert "não pertence" in r.text
    assert _datas() == []


def test_data_invalida_devolve_400_e_nao_grava(cliente):
    pid = _plataforma()
    r = cliente.post("/checkin", data={"mes": MES, "data": "15/01/2026", f"saldo_{pid}": "100,00", f"aporte_{pid}": "0"})
    assert r.status_code == 400
    assert _datas() == []


def test_mes_ja_gravado_abre_com_a_data_gravada(cliente):
    pid = _plataforma()
    cliente.post("/checkin", data={"mes": MES, "data": "2026-01-05", f"saldo_{pid}": "100,00", f"aporte_{pid}": "0"})
    r = cliente.get(f"/checkin?mes={MES}")
    assert 'value="2026-01-05"' in r.text


def test_ecra_diz_onde_vai_gravar(cliente):
    _plataforma()
    r = cliente.get(f"/checkin?mes={MES}&data=2026-01-20")
    assert "Vai gravar em <strong>01-2026</strong>, leitura de <strong>20-01-2026</strong>" in r.text


def test_ecra_agrupa_as_semanas_do_desafio_por_mes(cliente):
    _bondora_com_leitura_anterior()
    r = cliente.get(f"/checkin?mes={MES}")  # domingos 4, 11, 18 e 25 de janeiro: 10 €
    assert "<legend>01-2026 · 10,00 €</legend>" in r.text
    assert r.text.count('<fieldset class="mes-plano">') == 1
    assert r.text.count('type="checkbox" name="domingo_') == 4
    assert r.text.count(" checked>") == 4  # mês por registar: tudo marcado


def test_ecra_mostra_o_nome_da_categoria_e_nao_o_codigo(cliente):
    _plataforma()  # categoria 'viagens'
    r = cliente.get(f"/checkin?mes={MES}")
    assert "Viagens · Miguel" in r.text


def test_sair_pede_confirmacao_com_valores_por_gravar(cliente):
    _plataforma()
    r = cliente.get(f"/checkin?mes={MES}")
    assert 'id="form-sair"' in r.text and "confirm(" in r.text
    # o script liga-se ao formulário pelo id: o formulário tem de existir antes de o script correr
    assert r.text.index('id="form-sair"') < r.text.index("getElementById('form-sair')")


# --- caixas do desafio (esquema v4) ----------------------------------------------------------

def _confirmados():
    conn = db.connect()
    try:
        return [(r[0], r[1]) for r in conn.execute("SELECT domingo, mes FROM depositos_desafio ORDER BY domingo")]
    finally:
        conn.close()


def _post_bondora(cliente, pid, domingos, marcador=True, aporte="5,00"):
    dados = {"mes": MES, "data": "2026-01-31", f"saldo_{pid}": "1010,00", f"aporte_{pid}": aporte}
    if marcador:
        dados[f"desafio_{pid}"] = "1"
    if domingos:
        dados[f"domingo_{pid}"] = list(domingos)
    return cliente.post("/checkin", data=dados)


def test_gravar_guarda_so_os_domingos_marcados(cliente):
    pid = _bondora_com_leitura_anterior()
    r = _post_bondora(cliente, pid, ["2026-01-04", "2026-01-25"])  # 1 € + 4 €
    assert r.status_code == 200
    assert _confirmados() == [("2026-01-04", MES), ("2026-01-25", MES)]


def test_mes_gravado_reabre_com_as_caixas_confirmadas(cliente):
    pid = _bondora_com_leitura_anterior()
    _post_bondora(cliente, pid, ["2026-01-04", "2026-01-25"])
    r = cliente.get(f"/checkin?mes={MES}")
    assert r.text.count('type="checkbox" name="domingo_') == 4
    assert r.text.count(" checked>") == 2


def test_todas_desmarcadas_nao_confirma_nada(cliente):
    pid = _bondora_com_leitura_anterior()
    r = _post_bondora(cliente, pid, [], aporte="0,00")
    assert r.status_code == 200
    assert _confirmados() == []


def test_formulario_sem_marcador_confirma_todos(cliente):
    pid = _bondora_com_leitura_anterior()
    _post_bondora(cliente, pid, [], marcador=False, aporte="10,00")
    assert len(_confirmados()) == 4


def test_domingo_invalido_devolve_422_e_mantem_as_caixas(cliente):
    pid = _bondora_com_leitura_anterior()
    r = _post_bondora(cliente, pid, ["2026-01-04", "2026-02-01"])
    assert r.status_code == 422
    assert _confirmados() == []
    assert r.text.count(" checked>") == 1  # o 4/1 continua marcado; os outros não, como estavam


def test_ecra_tem_o_script_que_acerta_o_aporte(cliente):
    _bondora_com_leitura_anterior()
    r = cliente.get(f"/checkin?mes={MES}")
    assert 'data-valor="100"' in r.text and "caixa.checked ? valor : -valor" in r.text
