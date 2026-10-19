"""Check-in mensal do PWM: lógica sem web (linhas pré-preenchidas e gravação).

A camada web (main.py) só lê o formulário e chama estas funções; assim tudo o que
envolve dinheiro fica testável sem servidor.

Regras:
- O saldo anterior aparece como REFERÊNCIA, nunca pré-preenchido: um saldo pré-preenchido
  grava-se por engano sem ninguém dar por isso e falsifica o ganho do mês.
- O aporte vem pré-preenchido pelo plano da plataforma (editável).
- Gravação tudo-ou-nada: se uma linha tiver erro, nada é gravado.
- Saldo em branco = plataforma não tocada neste check-in (não grava nada).
- Aporte em branco = 0.
- Cada registo guarda a DATA da leitura (tem de pertencer ao mês e não pode ser futura). O aporte
  de plataformas com plano semanal (Desafio das 52 semanas) é sugerido a partir das datas das duas
  leituras; é só uma sugestão: o que fica gravado é o que o utilizador confirmar.
"""
from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from app import calc, planos


@dataclass(frozen=True)
class Linha:
    """Uma plataforma no ecrã de check-in."""

    plataforma_id: int
    nome: str
    categoria: str
    titular: str
    calcula_ganho: bool
    mes_anterior: str | None
    saldo_anterior_cent: int | None
    saldo_cent: int | None  # já registado neste mês (None = ainda não registado)
    aporte_cent: int  # registado neste mês, ou o plano se ainda não houver registo
    registado: bool
    data_leitura_anterior: date | None = None
    sugestao: planos.Sugestao | None = None  # aporte sugerido por um plano semanal
    nota_plano: str | None = None  # porque não há sugestão, quando devia haver


@dataclass(frozen=True)
class Entrada:
    """O que o utilizador escreveu para uma plataforma (texto cru do formulário)."""

    plataforma_id: int
    saldo: str
    aporte: str = ""


@dataclass(frozen=True)
class Gravado:
    plataforma_id: int
    nome: str
    resultado: calc.ResultadoMes
    avisos_plano: tuple[str, ...] = ()  # verificações do plano (ex.: rendimento implausível na Bondora)


@dataclass(frozen=True)
class Resultado:
    gravados: tuple[Gravado, ...] = ()
    erros: dict[int, str] = field(default_factory=dict)  # plataforma_id -> mensagem
    ignorados: tuple[int, ...] = ()  # saldo em branco

    @property
    def ok(self) -> bool:
        return not self.erros


def mes_de(data: date) -> str:
    return f"{data.year:04d}-{data.month:02d}"


def cent_para_texto(cent: int) -> str:
    """12345 -> '123,45' (sem milhares: serve de valor inicial de um campo de formulário)."""
    sinal = "-" if cent < 0 else ""
    inteiro, resto = divmod(abs(cent), 100)
    return f"{sinal}{inteiro},{resto:02d}"


def validar_mes(mes: str, hoje: date | None = None) -> None:
    """Formato AAAA-MM e nunca posterior ao mês atual (um ano mal escrito estragava o histórico)."""
    indice = calc.mes_para_indice(mes)  # levanta ValueError se o formato for inválido
    limite = calc.mes_para_indice(mes_de(hoje or date.today()))
    if indice > limite:
        raise ValueError(f"Mês no futuro: {mes}")


def data_por_defeito(mes: str, hoje: date | None = None) -> date:
    """Data da leitura sugerida: hoje, se `mes` for o mês atual; senão o último dia desse mês."""
    hoje = hoje or date.today()
    calc.mes_para_indice(mes)  # levanta ValueError se o formato for inválido
    if mes == mes_de(hoje):
        return hoje
    ano, m = int(mes[:4]), int(mes[5:7])
    return date(ano, m, calendar.monthrange(ano, m)[1])


def validar_data_leitura(data: date, mes: str, hoje: date | None = None) -> None:
    """A leitura tem de ser desse mês e não pode estar no futuro."""
    if mes_de(data) != mes:
        raise ValueError(f"A data da leitura ({data:%d/%m/%Y}) não pertence ao mês {mes}")
    if data > (hoje or date.today()):
        raise ValueError(f"Data da leitura no futuro: {data:%d/%m/%Y}")


def data_gravada(conn: sqlite3.Connection, mes: str) -> date | None:
    """A data da leitura já gravada nesse mês (a mais recente, se houver várias); None se não há nenhuma."""
    linha = conn.execute(
        """SELECT MAX(r.data_leitura) AS d FROM registos_mensais r
           JOIN plataformas p ON p.id = r.plataforma_id WHERE r.mes = ? AND p.ativa = 1""",
        (mes,),
    ).fetchone()
    return ler_data(linha["d"])


def ler_data(texto: str | None) -> date | None:
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _sugerir_plano(
    conn: sqlite3.Connection,
    plataforma_id: int,
    tem_anterior: bool,
    anterior: date | None,
    atual: date | None,
) -> tuple[planos.Sugestao | None, str | None]:
    """(sugestão, nota). Sem plano, sem data, ou no primeiro registo (saldo inicial): nada a sugerir."""
    plano = conn.execute(
        "SELECT data_inicio FROM planos WHERE plataforma_id = ? AND tipo = ? ORDER BY id LIMIT 1",
        (plataforma_id, planos.TIPO_DESAFIO_52),
    ).fetchone()
    if plano is None or atual is None or not tem_anterior:
        return None, None
    inicio = ler_data(plano["data_inicio"])
    if inicio is None:
        return None, "O plano tem uma data de início inválida: aporte do desafio não sugerido."
    if anterior is None:
        return None, "Sem data da leitura anterior: aporte do desafio não sugerido."
    if atual <= anterior:
        return None, f"A data da leitura tem de ser posterior à anterior ({anterior:%d/%m/%Y})."
    return planos.sugerir_desafio(anterior, atual, inicio), None


def linhas_checkin(conn: sqlite3.Connection, mes: str, data_leitura: date | None = None) -> list[Linha]:
    """Plataformas ativas, por ordem, com referência do mês anterior e aporte sugerido.

    Com `data_leitura`, as plataformas com plano semanal sugerem o aporte entre as duas leituras.
    """
    calc.mes_para_indice(mes)
    plataformas = conn.execute(
        """SELECT id, nome, categoria, titular, plano_mensal_cent, calcula_ganho
           FROM plataformas WHERE ativa = 1 ORDER BY ordem, id"""
    ).fetchall()

    linhas: list[Linha] = []
    for p in plataformas:
        # 'AAAA-MM' ordena corretamente como texto
        anterior = conn.execute(
            """SELECT mes, saldo_cent, data_leitura FROM registos_mensais
               WHERE plataforma_id = ? AND mes < ? ORDER BY mes DESC LIMIT 1""",
            (p["id"], mes),
        ).fetchone()
        atual = conn.execute(
            "SELECT saldo_cent, aporte_cent FROM registos_mensais WHERE plataforma_id = ? AND mes = ?",
            (p["id"], mes),
        ).fetchone()
        data_anterior = ler_data(anterior["data_leitura"]) if anterior else None
        sugestao, nota = _sugerir_plano(conn, p["id"], anterior is not None, data_anterior, data_leitura)
        if atual:
            aporte = atual["aporte_cent"]
        else:
            aporte = sugestao.total_cent if sugestao else p["plano_mensal_cent"]
        linhas.append(
            Linha(
                plataforma_id=p["id"],
                nome=p["nome"],
                categoria=p["categoria"],
                titular=p["titular"],
                calcula_ganho=bool(p["calcula_ganho"]),
                mes_anterior=anterior["mes"] if anterior else None,
                saldo_anterior_cent=anterior["saldo_cent"] if anterior else None,
                saldo_cent=atual["saldo_cent"] if atual else None,
                aporte_cent=aporte,
                registado=atual is not None,
                data_leitura_anterior=data_anterior,
                sugestao=sugestao,
                nota_plano=nota,
            )
        )
    return linhas


def _avisos_do_plano(
    conn: sqlite3.Connection, plataforma_id: int, mes: str, ganho_cent: int | None
) -> tuple[str, ...]:
    """Plausibilidade do rendimento nas plataformas com o Desafio das 52 semanas.

    Precisa das datas das duas leituras; sem elas (registos antigos) não avisa. Só apanha erros de
    aporte grandes: ao saldo atual da Bondora, um intervalo de 3-8 % deixa passar erros de ~10 €.
    """
    if ganho_cent is None:
        return ()
    desafio = conn.execute(
        "SELECT 1 FROM planos WHERE plataforma_id = ? AND tipo = ?", (plataforma_id, planos.TIPO_DESAFIO_52)
    ).fetchone()
    if desafio is None:
        return ()
    atual = conn.execute(
        "SELECT data_leitura FROM registos_mensais WHERE plataforma_id = ? AND mes = ?", (plataforma_id, mes)
    ).fetchone()
    anterior = conn.execute(
        """SELECT saldo_cent, data_leitura FROM registos_mensais
           WHERE plataforma_id = ? AND mes < ? ORDER BY mes DESC LIMIT 1""",
        (plataforma_id, mes),
    ).fetchone()
    data_atual = ler_data(atual["data_leitura"]) if atual else None
    data_anterior = ler_data(anterior["data_leitura"]) if anterior else None
    if data_atual is None or data_anterior is None:
        return ()
    aviso = planos.aviso_rendimento(ganho_cent, anterior["saldo_cent"], (data_atual - data_anterior).days)
    return (aviso,) if aviso else ()


def gravar_checkin(
    conn: sqlite3.Connection,
    mes: str,
    entradas: list[Entrada],
    hoje: date | None = None,
    data_leitura: date | None = None,
) -> Resultado:
    """Valida todas as linhas; se estiverem todas boas grava numa só transação.

    Regravar um mês já registado atualiza-o (não duplica). Devolve, por plataforma gravada,
    o ganho do mês e os avisos (ganho negativo, mês em falta).

    `data_leitura` (opcional) fica gravada em todos os registos desta gravação; sem ela, um registo
    novo fica sem data e um registo já datado mantém a sua.
    """
    validar_mes(mes, hoje)
    if data_leitura is not None:
        validar_data_leitura(data_leitura, mes, hoje)
    data_iso = data_leitura.isoformat() if data_leitura is not None else None

    ativas = {
        r["id"]: r
        for r in conn.execute("SELECT id, nome, calcula_ganho FROM plataformas WHERE ativa = 1")
    }
    erros: dict[int, str] = {}
    ignorados: list[int] = []
    a_gravar: list[tuple[int, int, int]] = []
    vistos: set[int] = set()

    for e in entradas:
        if e.plataforma_id not in ativas:
            erros[e.plataforma_id] = "Plataforma desconhecida ou inativa"
            continue
        if e.plataforma_id in vistos:
            erros[e.plataforma_id] = "Plataforma repetida no formulário"
            continue
        vistos.add(e.plataforma_id)
        if not e.saldo.strip():
            ignorados.append(e.plataforma_id)
            continue
        try:
            saldo = calc.euros_para_cent(e.saldo)
            aporte = calc.euros_para_cent(e.aporte) if e.aporte.strip() else 0
        except ValueError as exc:
            erros[e.plataforma_id] = str(exc)
            continue
        a_gravar.append((e.plataforma_id, saldo, aporte))

    if erros:
        return Resultado(erros=erros, ignorados=tuple(ignorados))

    with conn:  # transação: confirma tudo ou desfaz tudo
        conn.executemany(
            """INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(plataforma_id, mes) DO UPDATE SET
                   saldo_cent = excluded.saldo_cent,
                   aporte_cent = excluded.aporte_cent,
                   -- Uma linha que volta igual (o ecrã pré-preenche o que já está gravado) mantém a sua data:
                   -- reescrevê-la com a de hoje desloca a sugestão da Bondora do mês seguinte.
                   data_leitura = CASE
                       WHEN saldo_cent = excluded.saldo_cent AND aporte_cent = excluded.aporte_cent
                           THEN COALESCE(data_leitura, excluded.data_leitura)
                       ELSE COALESCE(excluded.data_leitura, data_leitura)
                   END""",
            [(pid, mes, saldo, aporte, data_iso) for pid, saldo, aporte in a_gravar],
        )

    gravados: list[Gravado] = []
    for pid, _, _ in a_gravar:
        regs = [
            calc.Registo(r["mes"], r["saldo_cent"], r["aporte_cent"])
            for r in conn.execute(
                "SELECT mes, saldo_cent, aporte_cent FROM registos_mensais WHERE plataforma_id = ? ORDER BY mes",
                (pid,),
            )
        ]
        serie = calc.calcular_serie(regs, bool(ativas[pid]["calcula_ganho"]))
        resultado = next(r for r in serie if r.mes == mes)
        try:  # os dados já estão gravados: uma verificação que rebente não pode dar erro 500
            avisos_plano = _avisos_do_plano(conn, pid, mes, resultado.ganho_cent)
        except Exception as exc:
            avisos_plano = (f"Não foi possível verificar o rendimento ({type(exc).__name__}: {exc}).",)
        gravados.append(Gravado(pid, ativas[pid]["nome"], resultado, avisos_plano))

    return Resultado(gravados=tuple(gravados), ignorados=tuple(ignorados))
