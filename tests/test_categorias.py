"""Categorias editáveis (esquema v5): lógica, ligação às plataformas, painel e rotas. Valores fictícios."""
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import backup, categorias, checkin, dashboard, db, plataformas
from app.main import app


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _plataforma(conn, nome="Conta Exemplo", categoria="investimento", ativa=1):
    cur = conn.execute(
        "INSERT INTO plataformas (nome, categoria, titular, ativa) VALUES (?, ?, 'Ana', ?)", (nome, categoria, ativa)
    )
    conn.commit()
    return cur.lastrowid


# --- criar ---------------------------------------------------------------------------------------------------

def test_base_nova_tem_as_categorias_de_origem_pela_ordem(conn):
    assert [(c.codigo, c.nome, c.cor) for c in categorias.listar(conn)] == list(db.CATEGORIAS_BASE)


def test_criar_gera_codigo_cor_livre_e_fica_no_fim(conn):
    codigo = categorias.criar(conn, "  Rendimento   extra ")
    lista = categorias.listar(conn)
    nova = lista[-1]
    assert codigo == nova.codigo == "rendimento_extra"
    assert nova.nome == "Rendimento extra"  # espaços a mais tirados
    assert nova.cor not in {c.cor for c in lista[:-1]}
    assert nova.ordem > max(c.ordem for c in lista[:-1])


def test_codigo_sem_acentos_nem_simbolos(conn):
    assert categorias.criar(conn, "Ações & Obrigações!") == "acoes_obrigacoes"


@pytest.mark.parametrize("repetido", ["Poupança", "poupanca", " POUPANÇA ", "Poupança!", "Fundo de Liberdade"])
def test_nomes_iguais_sem_contar_maiusculas_nem_acentos_sao_recusados(conn, repetido):
    with pytest.raises(ValueError, match="Já existe"):
        categorias.criar(conn, repetido)


@pytest.mark.parametrize("mau", ["", "   ", "!!!", "x" * 41])
def test_nomes_invalidos_sao_recusados(conn, mau):
    with pytest.raises(ValueError):
        categorias.criar(conn, mau)


def test_codigo_ocupado_por_categoria_renomeada_recebe_sufixo(conn):
    categorias.criar(conn, "Rendimento extra")
    categorias.renomear(conn, "rendimento_extra", "Side hustle")
    assert categorias.criar(conn, "Rendimento extra") == "rendimento_extra_2"


def test_cores_novas_repetem_se_quando_se_esgotam(conn):
    for i in range(len(categorias.CORES_NOVAS) + 2):
        categorias.criar(conn, f"Extra {i}")
    assert len(categorias.listar(conn)) == len(db.CATEGORIAS_BASE) + len(categorias.CORES_NOVAS) + 2


# --- renomear ------------------------------------------------------------------------------------------------

def test_renomear_muda_so_o_nome_e_a_plataforma_continua_ligada(conn):
    pid = _plataforma(conn, categoria="p2p")
    categorias.renomear(conn, "p2p", "Empréstimos P2P")
    assert categorias.rotulos(conn)["p2p"] == "Empréstimos P2P"
    assert conn.execute("SELECT categoria FROM plataformas WHERE id = ?", (pid,)).fetchone()[0] == "p2p"


def test_renomear_para_o_proprio_nome_com_outras_maiusculas_e_aceite(conn):
    categorias.renomear(conn, "cripto", "CRIPTO")
    assert categorias.rotulos(conn)["cripto"] == "CRIPTO"


def test_renomear_para_o_nome_de_outra_e_recusado(conn):
    with pytest.raises(ValueError, match="Investimento"):
        categorias.renomear(conn, "cripto", "investimento")


def test_renomear_inexistente(conn):
    with pytest.raises(LookupError):
        categorias.renomear(conn, "nao_existe", "Qualquer")


# --- apagar --------------------------------------------------------------------------------------------------

def test_apagar_sem_plataformas(conn):
    categorias.apagar(conn, "cripto")
    assert "cripto" not in categorias.codigos(conn)


def test_apagar_categoria_em_uso_e_recusado_mesmo_com_plataforma_inativa(conn):
    _plataforma(conn, categoria="viagens", ativa=0)
    with pytest.raises(ValueError, match="1 plataforma"):
        categorias.apagar(conn, "viagens")


def test_fundo_de_liberdade_nunca_se_apaga(conn):
    with pytest.raises(ValueError, match="fundo de liberdade"):
        categorias.apagar(conn, categorias.CATEGORIA_FUNDO)


def test_apagar_inexistente(conn):
    with pytest.raises(LookupError):
        categorias.apagar(conn, "nao_existe")


# --- ligação às plataformas e ao painel ------------------------------------------------------------------------

def test_plataforma_aceita_categoria_nova_e_recusa_inexistente(conn):
    codigo = categorias.criar(conn, "Rendimento extra")
    form = {"nome": "Conta Extra", "categoria": codigo, "titular": "Ana"}
    assert plataformas.validar(form, categorias.codigos(conn)).ok
    assert "categoria" in plataformas.validar({**form, "categoria": "nao_existe"}, categorias.codigos(conn)).erros


def test_painel_usa_nome_cor_e_ordem_da_base(conn):
    codigo = categorias.criar(conn, "Rendimento extra")
    a = _plataforma(conn, "Conta Extra", codigo)
    b = _plataforma(conn, "ETF Exemplo", "investimento")
    conn.execute("INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent) VALUES (?, '2026-10', 30000)", (a,))
    conn.execute("INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent) VALUES (?, '2026-10', 70000)", (b,))
    conn.commit()
    categorias.renomear(conn, "investimento", "ETF")

    painel = dashboard.construir_painel(conn, hoje=date(2026, 10, 21))

    assert [(s.categoria, s.rotulo) for s in painel.evolucao] == [("investimento", "ETF"), (codigo, "Rendimento extra")]
    assert [(f.rotulo, f.valor_cent) for f in painel.alocacao] == [("ETF", 70000), ("Rendimento extra", 30000)]
    assert painel.categorias[-1].codigo == codigo and painel.categorias[-1].cor.startswith("#")


def test_checkin_mostra_o_nome_da_categoria(conn):
    _plataforma(conn, categoria="p2p")
    categorias.renomear(conn, "p2p", "Empréstimos")
    assert checkin.linhas_checkin(conn, "2026-10")[0].categoria_nome == "Empréstimos"


# --- rotas -----------------------------------------------------------------------------------------------------

@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "teste.db"))
    with TestClient(app) as c:
        yield c


def test_ecra_mostra_a_seccao_e_a_lista_de_escolha_le_a_base(cliente):
    r = cliente.post("/categorias", data={"nome": "Rendimento extra"})
    assert r.status_code == 200 and "Categoria &#39;Rendimento extra&#39; criada" in r.text
    assert 'getElementById("categorias").scrollIntoView()' in r.text
    texto = cliente.get("/plataformas").text
    assert 'id="categorias"' in texto
    assert '<option value="rendimento_extra">Rendimento extra</option>' in texto


def test_criar_pela_rota_faz_copia_com_categorias_csv(cliente):
    cliente.post("/categorias", data={"nome": "Rendimento extra"})
    copia = backup.listar_copias(backup.pasta_backup_por_defeito())[-1]
    assert "Rendimento extra" in (copia / "categorias.csv").read_text(encoding="utf-8-sig")


def test_erro_ao_criar_mantem_o_texto_e_mostra_a_mensagem(cliente):
    r = cliente.post("/categorias", data={"nome": "poupanca"})
    assert r.status_code == 422
    assert "Já existe a categoria &#39;Poupança&#39;" in r.text
    assert 'value="poupanca"' in r.text
    assert 'getElementById("categorias").scrollIntoView()' in r.text


def test_renomear_e_apagar_pelas_rotas(cliente):
    assert "renomeada" in cliente.post("/categorias/cripto", data={"nome": "Airdrops"}).text
    assert 'value="Airdrops"' in cliente.get("/plataformas").text
    assert "apagada" in cliente.post("/categorias/cripto/apagar").text
    assert 'value="cripto"' not in cliente.get("/plataformas").text


def test_apagar_protegida_pela_rota_da_erro_e_nao_apaga(cliente):
    r = cliente.post(f"/categorias/{categorias.CATEGORIA_FUNDO}/apagar")
    assert r.status_code == 422
    c = db.connect(os.environ["PWM_DB"])
    assert categorias.CATEGORIA_FUNDO in categorias.codigos(c)


def test_rotas_com_categoria_inexistente_dao_404(cliente):
    assert cliente.post("/categorias/nao_existe", data={"nome": "X"}).status_code == 404
    assert cliente.post("/categorias/nao_existe/apagar").status_code == 404


def test_botao_apagar_so_aparece_nas_que_se_podem_apagar(cliente):
    cliente.post("/plataformas", data={"nome": "Conta Exemplo", "categoria": "p2p", "titular": "Ana"})
    texto = cliente.get("/plataformas").text
    assert 'formaction="/categorias/cripto/apagar"' in texto
    assert 'formaction="/categorias/p2p/apagar"' not in texto  # tem uma plataforma
    assert f'formaction="/categorias/{categorias.CATEGORIA_FUNDO}/apagar"' not in texto  # protegida
