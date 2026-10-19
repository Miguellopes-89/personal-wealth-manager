"""Painel do PWM (dashboard v1): lógica sem web.

Tudo o que envolve dinheiro fica aqui, em cêntimos (int), e é testável sem servidor; a camada web
(main.py) só chama `construir_painel` e entrega o resultado ao template.

Regras:
- Os cartões, a alocação e os planos mostram só plataformas ativas.
- Uma plataforma inativa conta no património e no ganho até ao seu último registo (decisão de 19/10/2026):
  desativá-la não reescreve o passado, e no mês seguinte o dinheiro aparece na plataforma de destino.
- O saldo de um mês sem registo é o do último registo anterior: uma plataforma que não foi tocada
  num check-in não desaparece do património nem faz o gráfico "cair".
- O painel mostra o último mês com registos (`Painel.mes`); `desatualizado` diz se já passou o mês atual.
- O "previsto" do Desafio das 52 semanas é o do plano (domingos até hoje), não o que foi depositado:
  o modelo de dados só guarda o aporte do mês, não cada depósito semanal.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from app import calc, checkin, db, planos

ROTULOS_CATEGORIA = {
    "conta_corrente": "Conta corrente",
    "transito": "Trânsito",
    "emergencia": "Fundo de emergência",
    "viagens": "Viagens",
    "p2p": "P2P",
    "investimento": "Investimento",
    "poupanca": "Poupança",
    "reforma": "Reforma",
    "numerario": "Numerário",
    "cripto": "Cripto",
}

TOTAL_DESAFIO_CENT = 100 * sum(range(1, planos.SEMANAS_DO_DESAFIO + 1))  # 1.378,00 €


@dataclass(frozen=True)
class Cartao:
    """Uma plataforma no painel, referida ao mês do painel."""

    plataforma_id: int
    nome: str
    categoria: str
    titular: str
    saldo_cent: int | None  # o do mês, ou o do último registo anterior; None se nunca foi registada
    registado: bool  # há registo no mês do painel
    ganho_cent: int | None
    aporte_cent: int | None  # aporte registado no mês (None se não há registo)
    plano_cent: int | None  # aporte esperado no mês; None = sem plano ou sem termo de comparação
    por_registar: bool  # tem plano e registo anterior, mas nada gravado no mês do painel
    avisos: tuple[str, ...] = ()

    @property
    def em_falta(self) -> bool:
        if self.por_registar:
            return True
        return self.plano_cent is not None and self.registado and (self.aporte_cent or 0) < self.plano_cent


@dataclass(frozen=True)
class Totais:
    patrimonio_cent: int
    variacao_cent: int | None  # face ao mês anterior (inclui aportes e ganho); None no primeiro mês
    ganho_cent: int | None  # soma dos ganhos do mês; None se nenhuma plataforma tem ganho calculável


@dataclass(frozen=True)
class SerieCategoria:
    categoria: str
    rotulo: str
    valores_cent: tuple[int, ...]  # um por mês de `Painel.meses`


@dataclass(frozen=True)
class FatiaAlocacao:
    categoria: str
    rotulo: str
    valor_cent: int
    percentagem: float  # só para mostrar; o valor de verdade é `valor_cent`


@dataclass(frozen=True)
class ProgressoDesafio:
    plataforma: str
    ano: int
    semana: int  # n-ésimo domingo do ano já passado (0 = ainda nenhum)
    previsto_cent: int  # soma do plano até hoje
    total_cent: int


@dataclass(frozen=True)
class Painel:
    mes: str
    mes_atual: str
    desatualizado: bool
    totais: Totais
    cartoes: tuple[Cartao, ...]
    meses: tuple[str, ...]  # do primeiro registo até `mes`, sem buracos
    evolucao: tuple[SerieCategoria, ...]
    alocacao: tuple[FatiaAlocacao, ...]
    desafios: tuple[ProgressoDesafio, ...]


def _meses_entre(primeiro: str, ultimo: str) -> list[str]:
    """['2026-07', ..., '2026-09'] com todos os meses do intervalo, tenham ou não registos."""
    inicio, fim = calc.mes_para_indice(primeiro), calc.mes_para_indice(ultimo)
    return [f"{n // 12:04d}-{n % 12 + 1:02d}" for n in range(inicio, fim + 1)]


def _saldo_em(registos: list[sqlite3.Row], mes: str) -> int | None:
    """Saldo do último registo com mês <= `mes` (os registos vêm ordenados por mês)."""
    saldo = None
    for r in registos:
        if r["mes"] > mes:
            break
        saldo = r["saldo_cent"]
    return saldo


def _saldos_por_mes(registos: list[sqlite3.Row], meses: list[str], ativa: bool) -> list[int | None]:
    """Saldo em cada mês. Uma inativa só conta até ao seu último registo (depois disso, None)."""
    ultimo = registos[-1]["mes"] if registos else None
    return [
        _saldo_em(registos, m) if ativa or (ultimo is not None and m <= ultimo) else None for m in meses
    ]


def _esperado_desafio(registos: list[sqlite3.Row], mes: str, inicio: date) -> int | None:
    """Aporte previsto pelo desafio entre a leitura anterior e a deste mês; None se faltarem datas."""
    atual = next((r for r in registos if r["mes"] == mes), None)
    anterior = next((r for r in reversed(registos) if r["mes"] < mes), None)
    if atual is None or anterior is None:
        return None
    d_atual, d_anterior = checkin.ler_data(atual["data_leitura"]), checkin.ler_data(anterior["data_leitura"])
    if d_atual is None or d_anterior is None or d_atual <= d_anterior:
        return None
    return planos.sugerir_desafio(d_anterior, d_atual, inicio).total_cent


def construir_painel(conn: sqlite3.Connection, hoje: date | None = None) -> Painel | None:
    """Painel do último mês com registos; None se ainda não há nenhum registo."""
    hoje = hoje or date.today()
    todas = conn.execute(
        """SELECT id, nome, categoria, titular, plano_mensal_cent, calcula_ganho, entra_alocacao, ativa
           FROM plataformas ORDER BY ordem, id"""
    ).fetchall()
    plataformas = [p for p in todas if p["ativa"]]
    registos: dict[int, list[sqlite3.Row]] = {p["id"]: [] for p in todas}
    for r in conn.execute(
        "SELECT plataforma_id, mes, saldo_cent, aporte_cent, data_leitura FROM registos_mensais ORDER BY mes"
    ):
        registos[r["plataforma_id"]].append(r)

    todos = [r["mes"] for lista in registos.values() for r in lista]
    if not todos:
        return None
    mes = max(todos)
    meses = _meses_entre(min(todos), mes)

    inicio_desafio: dict[int, date | None] = {}  # plataformas com o Desafio das 52 semanas
    for linha in conn.execute(
        "SELECT plataforma_id, data_inicio FROM planos WHERE tipo = ? ORDER BY id", (planos.TIPO_DESAFIO_52,)
    ):
        inicio_desafio.setdefault(linha["plataforma_id"], checkin.ler_data(linha["data_inicio"]))

    saldos = {p["id"]: _saldos_por_mes(registos[p["id"]], meses, bool(p["ativa"])) for p in todas}

    # Evolução: patrimónios por categoria e por mês (inativas incluídas até ao último registo)
    por_categoria: dict[str, list[int]] = {}
    for p in todas:
        acumulado = por_categoria.setdefault(p["categoria"], [0] * len(meses))
        for i, saldo in enumerate(saldos[p["id"]]):
            acumulado[i] += saldo or 0
    evolucao = tuple(
        SerieCategoria(c, ROTULOS_CATEGORIA.get(c, c), tuple(por_categoria[c]))
        for c in db.CATEGORIAS
        if c in por_categoria
    )
    total_por_mes = [sum(valores[i] for valores in por_categoria.values()) for i in range(len(meses))]

    # Ganho de cada plataforma em cada mês
    resultados: dict[tuple[int, str], calc.ResultadoMes] = {}
    for p in todas:
        lista = [calc.Registo(r["mes"], r["saldo_cent"], r["aporte_cent"]) for r in registos[p["id"]]]
        for res in calc.calcular_serie(lista, bool(p["calcula_ganho"])):
            resultados[(p["id"], res.mes)] = res

    cartoes: list[Cartao] = []
    for p in plataformas:
        pid = p["id"]
        res = resultados.get((pid, mes))
        registado = res is not None
        tem_anterior = any(r["mes"] < mes for r in registos[pid])
        tem_plano = pid in inicio_desafio or p["plano_mensal_cent"] > 0
        plano = None
        if registado and tem_anterior:  # no saldo inicial não há aporte a comparar
            if pid in inicio_desafio:
                if inicio_desafio[pid] is not None:
                    plano = _esperado_desafio(registos[pid], mes, inicio_desafio[pid])
            elif p["plano_mensal_cent"] > 0:
                plano = p["plano_mensal_cent"]
        cartoes.append(
            Cartao(
                plataforma_id=pid,
                nome=p["nome"],
                categoria=p["categoria"],
                titular=p["titular"],
                saldo_cent=saldos[pid][-1],
                registado=registado,
                ganho_cent=res.ganho_cent if res else None,
                aporte_cent=res.aporte_cent if res else None,
                plano_cent=plano,
                por_registar=tem_plano and tem_anterior and not registado,
                avisos=res.avisos if res else (),
            )
        )

    # O ganho do mês inclui o de uma conta fechada nesse mês (já não tem cartão, mas o dinheiro foi real)
    ganhos = [
        res.ganho_cent for p in todas
        if (res := resultados.get((p["id"], mes))) is not None and res.ganho_cent is not None
    ]
    totais = Totais(
        patrimonio_cent=total_por_mes[-1],
        variacao_cent=total_por_mes[-1] - total_por_mes[-2] if len(total_por_mes) > 1 else None,
        ganho_cent=sum(ganhos) if ganhos else None,
    )

    # Alocação: só as plataformas marcadas, agrupadas por categoria
    por_categoria_alocacao: dict[str, int] = {}
    for p in plataformas:
        saldo = saldos[p["id"]][-1]
        if p["entra_alocacao"] and saldo and saldo > 0:
            por_categoria_alocacao[p["categoria"]] = por_categoria_alocacao.get(p["categoria"], 0) + saldo
    total_alocacao = sum(por_categoria_alocacao.values())
    alocacao = tuple(
        FatiaAlocacao(c, ROTULOS_CATEGORIA.get(c, c), por_categoria_alocacao[c], por_categoria_alocacao[c] * 100 / total_alocacao)
        for c in db.CATEGORIAS
        if c in por_categoria_alocacao
    )

    # Desafio das 52 semanas: o previsto pelo plano até hoje (domingos do ano civil já passados)
    desafios: list[ProgressoDesafio] = []
    for p in plataformas:
        inicio = inicio_desafio.get(p["id"])
        if inicio is None or inicio > hoje:
            continue
        sugestao = planos.sugerir_desafio(date(hoje.year - 1, 12, 31), hoje, inicio)
        semana = sugestao.semanas[-1].numero if sugestao.semanas else 0
        desafios.append(ProgressoDesafio(p["nome"], hoje.year, semana, sugestao.total_cent, TOTAL_DESAFIO_CENT))

    mes_atual = checkin.mes_de(hoje)
    return Painel(
        mes=mes,
        mes_atual=mes_atual,
        desatualizado=mes < mes_atual,
        totais=totais,
        cartoes=tuple(cartoes),
        meses=tuple(meses),
        evolucao=evolucao,
        alocacao=alocacao,
        desafios=tuple(desafios),
    )


def dados_graficos(painel: Painel) -> dict:
    """Os dados dos dois gráficos, em estruturas simples para o template as passar ao JavaScript (em cêntimos)."""
    return {
        "meses": list(painel.meses),
        "evolucao": [
            {"categoria": s.categoria, "rotulo": s.rotulo, "valores_cent": list(s.valores_cent)}
            for s in painel.evolucao
        ],
        "alocacao": [
            {"categoria": f.categoria, "rotulo": f.rotulo, "valor_cent": f.valor_cent} for f in painel.alocacao
        ],
    }
