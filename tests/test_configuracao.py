import pytest

from app import configuracao, db


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def test_sem_referencia_devolve_none(conn):
    assert configuracao.obter_despesa_mensal(conn) is None


def test_gravar_atualizar_e_apagar(conn):
    configuracao.definir_despesa_mensal(conn, 150000)
    assert configuracao.obter_despesa_mensal(conn) == 150000
    configuracao.definir_despesa_mensal(conn, 120050)  # regravar atualiza, não duplica
    assert configuracao.obter_despesa_mensal(conn) == 120050
    assert conn.execute("SELECT COUNT(*) FROM configuracao").fetchone()[0] == 1
    configuracao.definir_despesa_mensal(conn, None)
    assert configuracao.obter_despesa_mensal(conn) is None


@pytest.mark.parametrize("texto, esperado", [("1500", 150000), ("1.500,00", 150000), ("1200,50 €", 120050), ("  ", None), ("", None)])
def test_validar_texto(texto, esperado):
    assert configuracao.validar_despesa_mensal(texto) == esperado


@pytest.mark.parametrize("texto", ["0", "0,00", "-100", "abc", "1.500"])
def test_validar_rejeita_zero_negativo_e_lixo(texto):
    with pytest.raises(ValueError):
        configuracao.validar_despesa_mensal(texto)


@pytest.mark.parametrize("cent", [0, -1])
def test_definir_rejeita_zero_e_negativo(conn, cent):
    with pytest.raises(ValueError):
        configuracao.definir_despesa_mensal(conn, cent)
    assert configuracao.obter_despesa_mensal(conn) is None
