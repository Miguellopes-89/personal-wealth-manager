"""Certificados de Aforro (v7): datas de vencimento, capitalização, cenários e gravação. Valores fictícios."""
from datetime import date
from fractions import Fraction

import pytest

from app import aforro, db

E = aforro.SERIES["E"]


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    c.execute("INSERT INTO plataformas (id, nome, categoria, titular) VALUES (1, 'Poupança Exemplo', 'poupanca', 'Ana')")
    c.commit()
    yield c
    c.close()


def _sub(data_sub=date(2023, 1, 10), unidades=1000, vu=100000, data_valor=date(2023, 1, 10)):
    return aforro.Subscricao(1, 1, "Poupança Exemplo", "E", data_sub, unidades, vu, data_valor)


# --- Datas -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("d, meses, esperado", [
    (date(2023, 1, 10), 3, date(2023, 4, 10)),
    (date(2023, 11, 15), 3, date(2024, 2, 15)),
    (date(2023, 11, 30), 3, date(2024, 3, 1)),  # 30/02 não existe: dia 1 do mês seguinte
    (date(2023, 8, 31), 3, date(2023, 12, 1)),  # 31/11 não existe
    (date(2023, 10, 31), 3, date(2024, 1, 31)),
])
def test_somar_meses(d, meses, esperado):
    assert aforro.somar_meses(d, meses) == esperado


def test_vencimento_final_e_10_anos_depois():
    assert aforro.vencimento_juros(date(2023, 1, 10), 40) == date(2033, 1, 10)
    assert aforro.vencimento_juros(date(2024, 2, 29), 40) == date(2034, 3, 1)


# --- Taxas e capitalização -----------------------------------------------------------------------------------

@pytest.mark.parametrize("k, esperado", [
    (1, 2000), (4, 2000),  # 1.º ano: sem prémio
    (5, 2500), (20, 2500),  # 2.º ao 5.º ano: +0,5 p.p.
    (21, 3000), (40, 3000),  # 6.º ao 10.º ano: +1 p.p.
])
def test_premio_de_permanencia(k, esperado):
    assert aforro.taxa_do_trimestre(E, k, 2000) == esperado


def test_taxa_base_limitada_entre_0_e_o_teto():
    assert aforro.taxa_do_trimestre(E, 1, 5000) == 3500
    assert aforro.taxa_do_trimestre(E, 21, 5000) == 4500
    assert aforro.taxa_do_trimestre(E, 1, -100) == 0


def test_capitalizar_um_trimestre_a_mao():
    # 1,00000 a 3 % ao ano: juro bruto 0,0075; líquido 0,0054 -> 1,00540
    assert aforro.capitalizar(E, 100000, 5, 2500) == 100540
    # 1,23457 a 2 %: 1,23457 × 0,005 × 0,72 = 0,004444452 -> 1,239014452 -> 1,23901
    assert aforro.capitalizar(E, 123457, 1, 2000) == 123901


def test_projetar_desde_a_subscricao_igual_ao_calculo_em_fracoes():
    s = _sub()
    p = aforro.projetar(s, [aforro.Cenario("c", "", 2000)])
    vu = Fraction(1)
    for k in range(1, 41):
        taxa = Fraction(aforro.taxa_do_trimestre(E, k, 2000), 100_000)
        vu = Fraction(int((vu + vu * taxa / 4 * Fraction(72, 100)) * 100000 + Fraction(1, 2)), 100000)
    assert p.valor_final_cent["c"] == int(1000 * vu * 100 + Fraction(1, 2))
    assert p.trimestres_em_falta == 40 and p.proximo_vencimento == date(2023, 4, 10)
    assert p.vencimento == date(2033, 1, 10) and not p.vencida


def test_parte_do_valor_do_extrato_e_conta_so_os_vencimentos_que_faltam():
    # Extrato no próprio dia do 8.º vencimento: esse já está capitalizado.
    s = _sub(vu=104000, data_valor=date(2025, 1, 10))
    p = aforro.projetar(s, [aforro.Cenario("c", "", 0)])
    assert p.trimestres_em_falta == 32 and p.proximo_vencimento == date(2025, 4, 10)
    assert p.proximo_vu["c"] == aforro.capitalizar(E, 104000, 9, 0)
    # Um dia antes: o 8.º ainda falta.
    p2 = aforro.projetar(_sub(vu=104000, data_valor=date(2025, 1, 9)), [aforro.Cenario("c", "", 0)])
    assert p2.trimestres_em_falta == 33


def test_cenarios_ordenam_os_valores_finais():
    s = _sub(vu=105000, data_valor=date(2026, 3, 1))
    lista = aforro.cenarios(E, 2700)
    p = aforro.projetar(s, lista)
    assert [c.codigo for c in lista] == ["minimo", "atual", "maximo"]
    assert p.valor_final_cent["minimo"] < p.valor_final_cent["atual"] < p.valor_final_cent["maximo"]
    assert aforro.cenarios(E, None)[1].codigo == "maximo"  # sem taxa atual só há os limites


def test_subscricao_vencida_fica_com_o_valor_do_extrato():
    s = _sub(vu=130000, data_valor=date(2033, 2, 1))
    p = aforro.projetar(s, aforro.cenarios(E, 2000))
    assert p.vencida and p.proximo_vencimento is None and p.trimestres_em_falta == 0
    assert set(p.valor_final_cent.values()) == {130000}


# --- Texto ----------------------------------------------------------------------------------------------------

def test_valor_unitario_de_texto():
    assert aforro.vu_de_texto("1,08734") == 108734
    assert aforro.vu_de_texto("1.08734") == 108734
    assert aforro.vu_para_texto(108734) == "1,08734"
    for mau in ("0,99999", "1,123456", "abc", "", "11"):
        with pytest.raises(ValueError):
            aforro.vu_de_texto(mau)


def test_taxa_de_texto():
    assert aforro.taxa_de_texto("2,951", E) == 2951
    assert aforro.taxa_de_texto("3,5", E) == 3500
    assert aforro.taxa_para_texto(2950) == "2,95" and aforro.taxa_para_texto(3000) == "3"
    for mau in ("3,6", "-1", "2,9512", "2.951"):  # 2.951 é ambíguo: usar vírgula
        with pytest.raises(ValueError):
            aforro.taxa_de_texto(mau, E)


def test_unidades_de_texto():
    assert aforro.unidades_de_texto("2.500") == 2500
    for mau in ("0", "2,5", "300000", ""):
        with pytest.raises(ValueError):
            aforro.unidades_de_texto(mau)


# --- Base de dados --------------------------------------------------------------------------------------------

FORM = {"plataforma_id": "1", "serie": "E", "data_subscricao": "2023-01-10", "unidades": "1000",
        "valor_unitario": "1,05", "data_valor": "2026-10-01"}


def test_criar_editar_apagar(conn):
    d, erros = aforro.validar(conn, FORM, date(2026, 11, 1))
    assert erros == {}
    sid = aforro.criar(conn, d)
    s = aforro.obter(conn, sid)
    assert (s.unidades, s.valor_unitario, s.data_valor, s.plataforma) == (1000, 105000, date(2026, 10, 1), "Poupança Exemplo")
    assert s.valor_cent == 105000

    d2, _ = aforro.validar(conn, {**FORM, "unidades": "800"}, date(2026, 11, 1))
    aforro.editar(conn, sid, d2)
    assert aforro.obter(conn, sid).unidades == 800

    aforro.apagar(conn, sid)
    assert aforro.listar(conn) == []
    with pytest.raises(LookupError):
        aforro.apagar(conn, sid)


@pytest.mark.parametrize("campo, valor", [
    ("plataforma_id", "9"), ("serie", "F"), ("data_subscricao", "2026-12-01"), ("data_subscricao", "10/01/2023"),
    ("unidades", "0"), ("valor_unitario", "0,9"), ("data_valor", "2022-12-31"), ("data_valor", "2026-11-02"),
])
def test_validar_recusa(conn, campo, valor):
    d, erros = aforro.validar(conn, {**FORM, campo: valor}, date(2026, 11, 1))
    assert d is None and campo in erros


def test_plataforma_com_subscricoes_nao_se_apaga(conn):
    d, _ = aforro.validar(conn, FORM, date(2026, 11, 1))
    aforro.criar(conn, d)
    with pytest.raises(Exception):
        conn.execute("DELETE FROM plataformas WHERE id = 1")


def test_taxa_atual_grava_com_a_data_e_apaga(conn):
    assert aforro.obter_taxa(conn) == (None, None)
    aforro.definir_taxa(conn, 2951, date(2026, 11, 1))
    assert aforro.obter_taxa(conn) == (2951, date(2026, 11, 1))
    aforro.definir_taxa(conn, None, date(2026, 11, 1))
    assert aforro.obter_taxa(conn) == (None, None)


def test_resumo_soma_as_subscricoes(conn):
    assert aforro.resumo(conn) is None
    for unidades in ("1000", "500"):
        d, _ = aforro.validar(conn, {**FORM, "unidades": unidades}, date(2026, 11, 1))
        aforro.criar(conn, d)
    aforro.definir_taxa(conn, 2000, date(2026, 11, 1))
    r = aforro.resumo(conn)
    assert r.valor_hoje_cent == 157500 and r.taxa_atual == 2000
    for c in r.cenarios:
        assert r.total_final_cent[c.codigo] == sum(p.valor_final_cent[c.codigo] for p in r.projecoes)
