import pytest

from app.calc import (
    AVISO_GANHO_NEGATIVO,
    AVISO_MES_EM_FALTA,
    Registo,
    calcular_ganho,
    calcular_serie,
    euros_para_cent,
    formatar_euros,
    mes_para_indice,
)


# --- calcular_ganho ---------------------------------------------------------

def test_ganho_simples():
    # 100 € + aporte de 5 € + 0,50 € de juros = 105,50 €
    assert calcular_ganho(10_550, 10_000, 500) == 50


def test_primeiro_registo_nao_tem_ganho():
    assert calcular_ganho(10_000, None, 0) is None


def test_levantamento_nao_e_perda():
    # levantou 10 € (aporte -10 €): 100 -> 90 € não é prejuízo
    assert calcular_ganho(9_000, 10_000, -1_000) == 0


def test_levantamento_com_juros():
    assert calcular_ganho(9_030, 10_000, -1_000) == 30


def test_ganho_negativo_e_possivel():
    assert calcular_ganho(9_900, 10_000, 0) == -100


# --- calcular_serie ---------------------------------------------------------

def test_serie_primeiro_mes_sem_ganho():
    res = calcular_serie([Registo("2026-10", 10_000, 0)])
    assert res[0].ganho_cent is None
    assert res[0].avisos == ()


def test_serie_meses_consecutivos():
    res = calcular_serie([
        Registo("2026-10", 10_000),
        Registo("2026-11", 10_560, 500),
        Registo("2026-12", 11_130, 500),
    ])
    assert [r.ganho_cent for r in res] == [None, 60, 70]
    assert all(r.avisos == () for r in res)


def test_serie_ordena_por_mes():
    res = calcular_serie([Registo("2026-11", 10_560, 500), Registo("2026-10", 10_000)])
    assert [r.mes for r in res] == ["2026-10", "2026-11"]
    assert res[1].ganho_cent == 60


def test_serie_atravessa_mudanca_de_ano():
    res = calcular_serie([Registo("2026-12", 10_000), Registo("2027-01", 10_050)])
    assert res[1].ganho_cent == 50
    assert res[1].avisos == ()


def test_serie_aviso_ganho_negativo():
    res = calcular_serie([Registo("2026-10", 10_000), Registo("2026-11", 9_000, 0)])
    assert res[1].ganho_cent == -1_000
    assert res[1].avisos == (AVISO_GANHO_NEGATIVO,)


def test_serie_aviso_mes_em_falta():
    res = calcular_serie([Registo("2026-10", 10_000), Registo("2026-12", 10_100, 0)])
    assert res[1].ganho_cent == 100
    assert res[1].avisos == (AVISO_MES_EM_FALTA,)


def test_serie_sem_calculo_de_ganho():
    # conta corrente / trânsito: salários e transferências não são lucro
    res = calcular_serie([Registo("2026-10", 100_000), Registo("2026-11", 250_000)], calcula_ganho=False)
    assert [r.ganho_cent for r in res] == [None, None]
    assert all(r.avisos == () for r in res)


def test_serie_rejeita_meses_duplicados():
    with pytest.raises(ValueError):
        calcular_serie([Registo("2026-10", 1), Registo("2026-10", 2)])


# --- mes_para_indice --------------------------------------------------------

def test_indice_meses_consecutivos():
    assert mes_para_indice("2027-01") - mes_para_indice("2026-12") == 1


@pytest.mark.parametrize("mau", ["2026-13", "2026-00", "26-10", "2026/10", "2026-1", "abc", ""])
def test_mes_invalido(mau):
    with pytest.raises(ValueError):
        mes_para_indice(mau)


# --- euros_para_cent --------------------------------------------------------

@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("12,50", 1_250),
        ("12.50", 1_250),
        ("12", 1_200),
        ("0,05", 5),
        ("1.234,56", 123_456),
        ("1,234.56", 123_456),
        ("1.234.567,89", 123_456_789),
        ("1 234,56 €", 123_456),
        ("-10,00", -1_000),
        ("12,345", 1_235),  # arredonda meio para cima
    ],
)
def test_euros_para_cent(texto, esperado):
    assert euros_para_cent(texto) == esperado


@pytest.mark.parametrize("mau", ["", "   ", "abc", "1.234", "NaN", "inf", "12,3,4", "1.234.56", "1.23.4", "1e3", "1,23,456.00", "12,"])
def test_euros_para_cent_rejeita(mau):
    with pytest.raises(ValueError):
        euros_para_cent(mau)


# --- formatar_euros ---------------------------------------------------------

@pytest.mark.parametrize(
    "cent, esperado",
    [
        (0, "0,00 €"),
        (5, "0,05 €"),
        (12_345, "123,45 €"),
        (123_456_789, "1.234.567,89 €"),
        (-1_000, "-10,00 €"),
    ],
)
def test_formatar_euros(cent, esperado):
    assert formatar_euros(cent) == esperado
