from datetime import date

import pytest

from app import planos


def test_primeiro_domingo_do_ano():
    assert planos.primeiro_domingo(2026) == date(2026, 1, 4)
    assert planos.primeiro_domingo(2027) == date(2027, 1, 3)
    assert planos.primeiro_domingo(2028) == date(2028, 1, 2)
    assert planos.primeiro_domingo(2023) == date(2023, 1, 1)  # 1 de janeiro a domingo


def test_numero_do_domingo():
    assert planos.numero_do_domingo(date(2026, 1, 4)) == 1
    assert planos.numero_do_domingo(date(2026, 10, 11)) == 41
    assert planos.numero_do_domingo(date(2026, 12, 27)) == 52
    assert planos.numero_do_domingo(date(2027, 1, 3)) == 1  # semana ISO 53 de 2026, mas 1.º domingo de 2027


def test_numero_do_domingo_rejeita_outros_dias():
    with pytest.raises(ValueError, match="domingo"):
        planos.numero_do_domingo(date(2026, 10, 12))  # segunda-feira


def test_valor_do_domingo_em_centimos():
    assert planos.valor_do_domingo(date(2026, 10, 11)) == 4100
    assert planos.valor_do_domingo(date(2026, 1, 4)) == 100
    assert planos.valor_do_domingo(date(2026, 12, 27)) == 5200


def test_53_domingo_do_ano_nao_tem_deposito():
    assert planos.numero_do_domingo(date(2028, 12, 31)) == 53
    assert planos.valor_do_domingo(date(2028, 12, 31)) is None


def test_sugerir_domingos_entre_duas_leituras():
    s = planos.sugerir_desafio(date(2026, 10, 13), date(2026, 11, 1))
    assert [(w.data, w.numero, w.valor_cent) for w in s.semanas] == [
        (date(2026, 10, 18), 42, 4200),
        (date(2026, 10, 25), 43, 4300),
        (date(2026, 11, 1), 44, 4400),
    ]
    assert s.total_cent == 12900
    assert [w.dia_da_leitura for w in s.semanas] == [False, False, True]


def test_domingo_da_leitura_anterior_nao_volta_a_contar():
    s = planos.sugerir_desafio(date(2026, 10, 11), date(2026, 10, 18))
    assert [w.numero for w in s.semanas] == [42]
    assert s.total_cent == 4200


def test_sem_domingos_entre_as_leituras():
    s = planos.sugerir_desafio(date(2026, 10, 12), date(2026, 10, 17))
    assert s.semanas == ()
    assert s.total_cent == 0


def test_sugerir_atravessa_a_viragem_do_ano():
    s = planos.sugerir_desafio(date(2026, 12, 20), date(2027, 1, 4))
    assert [(w.data, w.numero) for w in s.semanas] == [(date(2026, 12, 27), 52), (date(2027, 1, 3), 1)]
    assert s.total_cent == 5300  # 52 € + 1 €


def test_sugerir_salta_o_53_domingo():
    s = planos.sugerir_desafio(date(2028, 12, 25), date(2029, 1, 8))
    assert [(w.data, w.numero) for w in s.semanas] == [(date(2029, 1, 7), 1)]  # 31/12/2028 não conta
    assert s.total_cent == 100


def test_sugerir_ignora_domingos_antes_do_inicio_do_plano():
    s = planos.sugerir_desafio(date(2026, 10, 13), date(2026, 11, 1), data_inicio=date(2026, 10, 25))
    assert [w.numero for w in s.semanas] == [43, 44]


def test_leitura_atual_tem_de_ser_posterior():
    with pytest.raises(ValueError, match="posterior"):
        planos.sugerir_desafio(date(2026, 11, 1), date(2026, 11, 1))
    with pytest.raises(ValueError, match="posterior"):
        planos.sugerir_desafio(date(2026, 11, 2), date(2026, 11, 1))


def test_rendimento_anualizado():
    # novembro: 15,00 € sobre 5000,00 € em 19 dias
    assert planos.rendimento_anualizado(1500, 500000, 19) == pytest.approx(0.0576, abs=0.0001)


def test_sem_aviso_dentro_do_intervalo_esperado():
    assert planos.aviso_rendimento(1500, 500000, 19) is None


def test_aviso_quando_o_rendimento_sai_do_intervalo():
    alto = planos.aviso_rendimento(1500 + 4400, 500000, 19)  # depósito de 44 € feito mas não declarado
    assert "22,7 %" in alto
    assert "esperado entre 3,0 % e 8,0 %" in alto
    baixo = planos.aviso_rendimento(1500 - 4400, 500000, 19)  # depósito declarado que não chegou
    assert "-11,1 %" in baixo


def test_rendimento_nao_calculavel():
    assert planos.rendimento_anualizado(100, 0, 19) is None
    assert planos.rendimento_anualizado(100, 1000, 0) is None
    assert planos.aviso_rendimento(100, 0, 19) is None


def test_sugestao_agrupada_por_mes():
    s = planos.sugerir_desafio(date(2026, 10, 13), date(2026, 11, 1))
    grupos = s.por_mes
    assert [(g.mes, g.total_cent, [w.numero for w in g.semanas]) for g in grupos] == [
        ("2026-10", 8500, [42, 43]),
        ("2026-11", 4400, [44]),
    ]
    assert [g.tem_dia_da_leitura for g in grupos] == [False, True]
    assert sum(g.total_cent for g in grupos) == s.total_cent


def test_sugestao_sem_semanas_nao_tem_meses():
    s = planos.sugerir_desafio(date(2026, 10, 19), date(2026, 10, 24))
    assert s.semanas == () and s.por_mes == ()
