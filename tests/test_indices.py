"""Índices de referência (esquema v6): valores, gestão e gravação no check-in. Valores fictícios."""
from datetime import date

import pytest

from app import categorias, checkin, db, indices
from app.checkin import Entrada

HOJE = date(2026, 11, 2)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _plataforma(conn, nome="Corretora", categoria="investimento"):
    cur = conn.execute("INSERT INTO plataformas (nome, categoria, titular) VALUES (?, ?, 'Ana')", (nome, categoria))
    conn.commit()
    return cur.lastrowid


# --- Valores ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("130,145", 1301450),
    ("118,42", 1184200),
    ("100", 1000000),
    ("1.234,5678", 12345678),
    ("0,00005", 1),  # arredonda à 4.ª casa
    (" 99,9 ", 999000),
])
def test_valor_de_texto(texto, esperado):
    assert indices.valor_de_texto(texto) == esperado


@pytest.mark.parametrize("texto", ["", "abc", "0", "-5", "0,00004", "130.145", "1e3", "2000000000"])
def test_valor_invalido(texto):
    with pytest.raises(ValueError):
        indices.valor_de_texto(texto)


@pytest.mark.parametrize("valor, texto", [(1301450, "130,145"), (1000000, "100"), (1, "0,0001"), (1184200, "118,42")])
def test_valor_para_texto_e_ida_e_volta(valor, texto):
    assert indices.valor_para_texto(valor) == texto
    assert indices.valor_de_texto(texto) == valor


# --- Gestão ----------------------------------------------------------------------------------------------------

def test_criar_editar_listar(conn):
    a = indices.criar(conn, "  Ações   mundo ", "investimento")
    b = indices.criar(conn, "Inflação", "")
    lista = indices.listar(conn)
    assert [(i.nome, i.perimetro, i.ativo) for i in lista] == [("Ações mundo", "investimento", True), ("Inflação", None, True)]
    assert lista[0].ordem < lista[1].ordem

    indices.editar(conn, a, "MSCI World", None)
    assert indices.obter(conn, a).nome == "MSCI World" and indices.obter(conn, a).perimetro is None
    assert indices.obter(conn, b).nome == "Inflação"


@pytest.mark.parametrize("nome, perimetro, mensagem", [
    ("", None, "nome"),
    ("x" * 41, None, "máximo"),
    ("---", None, "letra"),
    ("inflacao", None, "Já existe"),  # sem contar maiúsculas nem acentos
    ("Outro", "nao_existe", "Categoria inexistente"),
])
def test_criar_recusa(conn, nome, perimetro, mensagem):
    indices.criar(conn, "Inflação", None)
    with pytest.raises(ValueError, match=mensagem):
        indices.criar(conn, nome, perimetro)
    assert len(indices.listar(conn)) == 1


def test_editar_pode_manter_o_proprio_nome(conn):
    a = indices.criar(conn, "Inflação", None)
    indices.editar(conn, a, "INFLAÇÃO", None)
    assert indices.obter(conn, a).nome == "INFLAÇÃO"
    with pytest.raises(LookupError):
        indices.editar(conn, 99, "X", None)


def test_desativar_tira_dos_ativos(conn):
    a = indices.criar(conn, "Inflação", None)
    indices.definir_ativo(conn, a, False)
    assert indices.listar(conn, so_ativos=True) == []
    indices.definir_ativo(conn, a, True)
    assert len(indices.listar(conn, so_ativos=True)) == 1
    with pytest.raises(LookupError):
        indices.definir_ativo(conn, 99, True)


def test_apagar_so_sem_valores(conn):
    a = indices.criar(conn, "Inflação", None)
    with conn:
        indices.gravar_valores(conn, "2026-10", {a: 1184200})
    with pytest.raises(ValueError, match="desativa"):
        indices.apagar(conn, a)
    indices.apagar_valor(conn, a, "2026-10")
    indices.apagar(conn, a)
    assert indices.listar(conn) == []
    with pytest.raises(LookupError):
        indices.apagar_valor(conn, a, "2026-10")


def test_categoria_usada_como_perimetro_nao_se_apaga(conn):
    codigo = categorias.criar(conn, "Extra")
    a = indices.criar(conn, "Índice extra", codigo)
    with pytest.raises(ValueError, match="perímetro"):
        categorias.apagar(conn, codigo)
    indices.editar(conn, a, "Índice extra", None)
    categorias.apagar(conn, codigo)


# --- Check-in --------------------------------------------------------------------------------------------------

def test_checkin_grava_saldos_e_indices_juntos(conn):
    pid = _plataforma(conn)
    a = indices.criar(conn, "Ações mundo", "investimento")
    b = indices.criar(conn, "Inflação", None)

    r = checkin.gravar_checkin(conn, "2026-11", [Entrada(pid, "1000,00")], HOJE, valores_indices={a: "130,145", b: ""})

    assert r.ok and r.indices_gravados == 1
    assert indices.valores_do_mes(conn, "2026-11") == {a: 1301450}  # em branco não grava


def test_checkin_so_com_indices_e_regravar_substitui(conn):
    a = indices.criar(conn, "Ações mundo", "investimento")
    checkin.gravar_checkin(conn, "2026-10", [], HOJE, valores_indices={a: "120"})
    r = checkin.gravar_checkin(conn, "2026-10", [], HOJE, valores_indices={a: "121,5"})
    assert r.ok
    assert indices.valores(conn, a) == {"2026-10": 1215000}
    checkin.gravar_checkin(conn, "2026-10", [], HOJE, valores_indices={a: " "})  # em branco não apaga
    assert indices.valores(conn, a) == {"2026-10": 1215000}


def test_checkin_tudo_ou_nada_com_indices(conn):
    pid = _plataforma(conn)
    a = indices.criar(conn, "Ações mundo", "investimento")

    r = checkin.gravar_checkin(conn, "2026-11", [Entrada(pid, "1000,00")], HOJE, valores_indices={a: "abc"})
    assert not r.ok and a in r.erros_indices
    assert conn.execute("SELECT COUNT(*) FROM registos_mensais").fetchone()[0] == 0

    r = checkin.gravar_checkin(conn, "2026-11", [Entrada(pid, "xyz")], HOJE, valores_indices={a: "130"})
    assert not r.ok and pid in r.erros
    assert indices.valores_do_mes(conn, "2026-11") == {}


def test_checkin_recusa_indice_inativo_ou_inexistente(conn):
    a = indices.criar(conn, "Ações mundo", "investimento")
    indices.definir_ativo(conn, a, False)
    r = checkin.gravar_checkin(conn, "2026-11", [], HOJE, valores_indices={a: "130", 99: "1"})
    assert set(r.erros_indices) == {a, 99}
    assert indices.valores_do_mes(conn, "2026-11") == {}
