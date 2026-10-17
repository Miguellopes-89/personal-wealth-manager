"""Planos de aporte do PWM: o Desafio das 52 semanas da Bondora.

Regra (confirmada a 14/10/2026): depósito semanal ao domingo; o n-ésimo domingo do ano civil
deposita n euros, com n entre 1 e 52. O 1.º domingo do ano é o primeiro domingo em ou depois
de 1 de janeiro. Em anos com 53 domingos (ex.: 2028) o 53.º fica sem depósito.

Em 2026 coincide com a semana ISO (1.º domingo = 4/1; 41.º = 11/10, confirmado pelo extrato).
Em 2027 divergem: o 1.º domingo é 3/1, e a semana ISO 1 só acaba a 10/1.

Todos os valores em cêntimos (int).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

TIPO_DESAFIO_52 = "desafio_52_semanas"
SEMANAS_DO_DESAFIO = 52
_DOMINGO = 6  # date.weekday(): segunda = 0 ... domingo = 6


@dataclass(frozen=True)
class Semana:
    data: date  # o domingo
    numero: int  # n-ésimo domingo do ano
    valor_cent: int
    dia_da_leitura: bool = False  # domingo igual ao dia da leitura: o depósito pode ainda não estar no saldo


@dataclass(frozen=True)
class Sugestao:
    semanas: tuple[Semana, ...]

    @property
    def total_cent(self) -> int:
        return sum(s.valor_cent for s in self.semanas)


def _proximo_domingo(d: date) -> date:
    """O primeiro domingo em ou depois de `d`."""
    return d + timedelta(days=(_DOMINGO - d.weekday()) % 7)


def primeiro_domingo(ano: int) -> date:
    return _proximo_domingo(date(ano, 1, 1))


def numero_do_domingo(d: date) -> int:
    """1 para o 1.º domingo do ano civil, 2 para o seguinte, etc."""
    if d.weekday() != _DOMINGO:
        raise ValueError(f"{d.isoformat()} não é domingo")
    return (d - primeiro_domingo(d.year)).days // 7 + 1


def valor_do_domingo(d: date) -> int | None:
    """Cêntimos a depositar nesse domingo; None se for o 53.º (o desafio só tem 52 semanas)."""
    n = numero_do_domingo(d)
    return n * 100 if n <= SEMANAS_DO_DESAFIO else None


def sugerir_desafio(
    leitura_anterior: date,
    leitura_atual: date,
    data_inicio: date | None = None,
) -> Sugestao:
    """Domingos com leitura_anterior < domingo <= leitura_atual (cada domingo conta uma só vez).

    O domingo da leitura anterior já está no saldo dessa leitura; o da leitura atual entra,
    marcado em `dia_da_leitura`. Domingos antes de `data_inicio` são ignorados.
    """
    if leitura_atual <= leitura_anterior:
        raise ValueError("A leitura atual tem de ser posterior à anterior")
    semanas: list[Semana] = []
    d = _proximo_domingo(leitura_anterior + timedelta(days=1))
    while d <= leitura_atual:
        if data_inicio is None or d >= data_inicio:
            valor = valor_do_domingo(d)
            if valor is not None:
                semanas.append(Semana(d, numero_do_domingo(d), valor, dia_da_leitura=(d == leitura_atual)))
        d += timedelta(days=7)
    return Sugestao(tuple(semanas))


# Intervalo anual em que o rendimento do Go & Grow é plausível (taxa de ~6 %, que a Bondora pode alterar).
# Serve para apanhar um aporte mal contado: um depósito a mais ou a menos desloca o ganho para fora dele.
RENDIMENTO_ESPERADO = (0.03, 0.08)


def rendimento_anualizado(ganho_cent: int, saldo_anterior_cent: int, dias: int) -> float | None:
    """Ganho / saldo anterior, anualizado pelos dias entre leituras (base 365). None se não der para calcular."""
    if saldo_anterior_cent <= 0 or dias <= 0:
        return None
    return ganho_cent / saldo_anterior_cent * 365 / dias


def aviso_rendimento(
    ganho_cent: int,
    saldo_anterior_cent: int,
    dias: int,
    limites: tuple[float, float] = RENDIMENTO_ESPERADO,
) -> str | None:
    """Mensagem se o rendimento anualizado implícito sair do intervalo esperado; None se estiver normal."""
    taxa = rendimento_anualizado(ganho_cent, saldo_anterior_cent, dias)
    if taxa is None or limites[0] <= taxa <= limites[1]:
        return None

    def pct(x: float) -> str:
        return f"{x * 100:.1f}".replace(".", ",")

    return (
        f"Rendimento anualizado implícito de {pct(taxa)} % (esperado entre {pct(limites[0])} % e "
        f"{pct(limites[1])} %): confirma o saldo e se todos os depósitos semanais foram contados no aporte."
    )
