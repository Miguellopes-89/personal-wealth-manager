"""Cálculos financeiros do PWM.

Todos os valores monetários circulam em cêntimos (int), nunca em float:
0,1 + 0,2 em float não dá 0,3, e num registo financeiro essa deriva acumula-se.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

AVISO_GANHO_NEGATIVO = "ganho_negativo"
AVISO_MES_EM_FALTA = "mes_em_falta"


@dataclass(frozen=True)
class Registo:
    mes: str  # 'AAAA-MM'
    saldo_cent: int
    aporte_cent: int = 0  # levantamentos são aportes negativos


@dataclass(frozen=True)
class ResultadoMes:
    mes: str
    saldo_cent: int
    aporte_cent: int
    ganho_cent: int | None  # None = sem ganho calculável (primeiro registo ou plataforma sem ganho)
    avisos: tuple[str, ...] = ()


def mes_para_indice(mes: str) -> int:
    """'2026-10' -> número sequencial de meses, para medir intervalos entre registos."""
    try:
        ano_txt, mes_txt = mes.split("-")
        ano, m = int(ano_txt), int(mes_txt)
    except ValueError:
        raise ValueError(f"Mês inválido: {mes!r} (esperado AAAA-MM)") from None
    if len(ano_txt) != 4 or len(mes_txt) != 2 or not 1 <= m <= 12:
        raise ValueError(f"Mês inválido: {mes!r} (esperado AAAA-MM)")
    return ano * 12 + (m - 1)


def formatar_mes(mes: str) -> str:
    """'2026-09' -> '09-2026', o formato dos meses no ecrã (os dados e os formulários ficam em AAAA-MM)."""
    mes_para_indice(mes)  # valida o formato (levanta ValueError)
    return f"{mes[5:7]}-{mes[:4]}"


def calcular_ganho(saldo_cent: int, saldo_anterior_cent: int | None, aporte_cent: int) -> int | None:
    """ganho = saldo - saldo anterior - aporte. Sem registo anterior não há ganho."""
    if saldo_anterior_cent is None:
        return None
    return saldo_cent - saldo_anterior_cent - aporte_cent


def calcular_serie(registos: list[Registo], calcula_ganho: bool = True) -> list[ResultadoMes]:
    """Calcula o ganho de cada mês de uma plataforma, por ordem cronológica.

    Avisos:
    - ganho_negativo: o saldo desceu mais do que o aporte explica (erro de registo ou perda real).
    - mes_em_falta: há meses sem registo entre este e o anterior; o ganho cobre vários meses.
    """
    ordenados = sorted(registos, key=lambda r: mes_para_indice(r.mes))
    meses = [r.mes for r in ordenados]
    if len(set(meses)) != len(meses):
        raise ValueError("Meses duplicados nos registos")

    resultados: list[ResultadoMes] = []
    anterior: Registo | None = None
    for reg in ordenados:
        ganho = None
        avisos: list[str] = []
        if calcula_ganho and anterior is not None:
            ganho = calcular_ganho(reg.saldo_cent, anterior.saldo_cent, reg.aporte_cent)
            if ganho < 0:
                avisos.append(AVISO_GANHO_NEGATIVO)
            if mes_para_indice(reg.mes) - mes_para_indice(anterior.mes) > 1:
                avisos.append(AVISO_MES_EM_FALTA)
        resultados.append(ResultadoMes(reg.mes, reg.saldo_cent, reg.aporte_cent, ganho, tuple(avisos)))
        anterior = reg
    return resultados


# Teto de qualquer valor introduzido: 10 mil milhões de euros. Muito acima de um património pessoal real e
# muito abaixo do INTEGER do SQLite (2^63-1): um valor maior rebentava com OverflowError (erro 500) ao gravar.
LIMITE_CENT = 10**12

_NUMERO = re.compile(r"[+-]?\d+(\.\d+)?")
# Parte inteira com separador de milhares: grupos de 3 depois do primeiro ('1.234.567', não '1.23.4')
_MILHARES = {sep: re.compile(rf"[+-]?\d{{1,3}}(\{sep}\d{{3}})+") for sep in ".,"}


def texto_para_decimal(texto: str) -> Decimal:
    """Converte texto digitado ('12,50', '1.234,56', '12.5') num Decimal exato.

    Rejeita o caso ambíguo '1.234' (mil duzentos e trinta e quatro, ou 1,234?) e separadores de milhares
    mal colocados ('1.234.56' não vira 123.456). Serve os euros e os valores dos índices.
    """
    t = texto.strip().replace("€", "").replace(" ", "").replace("\u00a0", "")
    if not t:
        raise ValueError("Valor vazio")
    _validar_milhares(t, texto)
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")  # 1.234,56
        else:
            t = t.replace(",", "")  # 1,234.56
    elif "," in t:
        t = t.replace(",", ".")
    elif "." in t:
        if t.count(".") > 1:
            t = t.replace(".", "")  # 1.234.567
        elif len(t.split(".")[1]) == 3:
            raise ValueError(f"Valor ambíguo: {texto!r} (use vírgula para as casas decimais)")
    if not _NUMERO.fullmatch(t):  # rejeita '1e3' e restos que o Decimal aceitaria
        raise ValueError(f"Valor inválido: {texto!r}")
    try:
        valor = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"Valor inválido: {texto!r}") from None
    if not valor.is_finite():
        raise ValueError(f"Valor inválido: {texto!r}")
    return valor


def euros_para_cent(texto: str) -> int:
    """Converte texto digitado ('12,50', '1.234,56', '12.5') em cêntimos (regras em `texto_para_decimal`)."""
    valor = texto_para_decimal(texto)
    cent = int((valor * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if abs(cent) > LIMITE_CENT:
        raise ValueError(f"Valor fora do intervalo aceite: {texto!r}")
    return cent


def _validar_milhares(t: str, original: str) -> None:
    """Se há um separador de milhares, a parte inteira tem de estar em grupos de 3."""
    if "," in t and "." in t:
        decimal = "," if t.rfind(",") > t.rfind(".") else "."
        milhares = "." if decimal == "," else ","
        inteiro = t[: t.rfind(decimal)]
    elif t.count(".") > 1:
        milhares, inteiro = ".", t
    else:
        return
    if not _MILHARES[milhares].fullmatch(inteiro):
        raise ValueError(f"Separador de milhares mal colocado: {original!r}")


def formatar_euros(cent: int) -> str:
    """12345 -> '123,45 €'; 123456789 -> '1.234.567,89 €'."""
    sinal = "-" if cent < 0 else ""
    inteiro, resto = divmod(abs(cent), 100)
    return f"{sinal}{inteiro:,}".replace(",", ".") + f",{resto:02d} €"
