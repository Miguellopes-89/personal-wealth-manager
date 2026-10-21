"""Gestão das plataformas do PWM: criar, editar, desativar (fechar conta), reativar e apagar.

Lógica sem web, como em `checkin.py`: a camada web só lê o formulário e chama estas funções.

Regras:
- Fechar uma conta = saldo 0 (decisão de 19/10/2026, opção A). Só se desativa uma plataforma cujo último
  registo tenha saldo 0 (ou que não tenha registos). O 0 grava-se no check-in em que o dinheiro já está no
  destino, com o levantamento como aporte negativo; no destino entra como aporte positivo. Assim uma
  transferência entre plataformas não conta como poupança nova e o património do passado não muda.
  Desativar nunca apaga histórico nem grava registos.
- Só se apaga uma plataforma sem registos (serve para corrigir uma criada por engano).
- Mudar a categoria ou o "calcula ganho" de uma plataforma muda também o passado no painel.
- Posição (sessão 14): escolhe-se numa lista com as plataformas ativas da mesma categoria ("no início",
  "depois de X", "no fim"). A coluna `ordem` continua a ser uma ordem global (o check-in e a tabela mostram
  uma lista única), por isso a plataforma é posta no sítio escolhido e todas são renumeradas 10, 20, 30…,
  sem mudar a posição relativa das outras. As inativas ficam fora da lista.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from app import calc, db, planos

POSICAO_FIM = ""  # no fim da categoria (por defeito numa plataforma nova ou que muda de categoria)
POSICAO_INICIO = "inicio"
PREFIXO_DEPOIS = "depois:"  # "depois:<id>" = logo a seguir a essa plataforma
PASSO_ORDEM = 10


class PosicaoInvalida(ValueError):
    """A plataforma escolhida em "Posição" não serve (outra categoria, inativa, inexistente ou a própria)."""


@dataclass(frozen=True)
class Dados:
    """Uma plataforma já validada, pronta a gravar."""

    nome: str
    categoria: str
    titular: str
    finalidade: str | None
    plano_mensal_cent: int
    calcula_ganho: bool
    entra_alocacao: bool
    posicao: str  # POSICAO_FIM, POSICAO_INICIO ou "depois:<id>"
    desafio_inicio: date | None  # None = sem Desafio das 52 semanas


@dataclass(frozen=True)
class Validacao:
    dados: Dados | None = None
    erros: dict[str, str] = field(default_factory=dict)  # campo -> mensagem

    @property
    def ok(self) -> bool:
        return not self.erros


def validar(form: dict[str, str], categorias_validas: Iterable[str] | None = None) -> Validacao:
    """Valida o formulário (textos crus). Checkboxes: presentes = marcadas.

    `categorias_validas`: os códigos da tabela categorias (a web passa os da base); por defeito, os de origem.
    """
    erros: dict[str, str] = {}
    nome = (form.get("nome") or "").strip()
    titular = (form.get("titular") or "").strip()
    categoria = (form.get("categoria") or "").strip()
    if not nome:
        erros["nome"] = "Indica o nome"
    if not titular:
        erros["titular"] = "Indica o titular"
    if categoria not in (db.CATEGORIAS if categorias_validas is None else set(categorias_validas)):
        erros["categoria"] = "Escolhe uma categoria"

    plano = 0
    texto_plano = (form.get("plano_mensal") or "").strip()
    if texto_plano:
        try:
            plano = calc.euros_para_cent(texto_plano)
        except ValueError as exc:
            erros["plano_mensal"] = str(exc)
        else:
            if plano < 0:
                erros["plano_mensal"] = "O plano mensal não pode ser negativo"

    posicao = (form.get("posicao") or "").strip()
    if _id_depois(posicao) is None and posicao not in (POSICAO_FIM, POSICAO_INICIO):
        erros["posicao"] = "Escolhe a posição na lista"

    inicio = None
    if form.get("desafio"):
        try:
            inicio = date.fromisoformat((form.get("desafio_inicio") or "").strip())
        except ValueError:
            erros["desafio_inicio"] = "Indica a data de início do desafio (AAAA-MM-DD)"

    if erros:
        return Validacao(erros=erros)
    return Validacao(
        Dados(
            nome=nome,
            categoria=categoria,
            titular=titular,
            finalidade=(form.get("finalidade") or "").strip() or None,
            plano_mensal_cent=plano,
            calcula_ganho=bool(form.get("calcula_ganho")),
            entra_alocacao=bool(form.get("entra_alocacao")),
            posicao=posicao,
            desafio_inicio=inicio,
        )
    )


def listar(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Todas as plataformas (ativas primeiro), com o número de registos e o último mês registado."""
    return conn.execute(
        """SELECT p.*, COUNT(r.mes) AS n_registos, MAX(r.mes) AS ultimo_mes,
                  (SELECT data_inicio FROM planos q WHERE q.plataforma_id = p.id AND q.tipo = ?
                   ORDER BY q.id LIMIT 1) AS desafio_inicio
           FROM plataformas p LEFT JOIN registos_mensais r ON r.plataforma_id = p.id
           GROUP BY p.id ORDER BY p.ativa DESC, p.ordem, p.id""",
        (planos.TIPO_DESAFIO_52,),
    ).fetchall()


def obter(conn: sqlite3.Connection, plataforma_id: int) -> sqlite3.Row | None:
    return next((p for p in listar(conn) if p["id"] == plataforma_id), None)


def _id_depois(posicao: str) -> int | None:
    """O id em "depois:<id>"; None se o texto não tiver essa forma."""
    resto = posicao.removeprefix(PREFIXO_DEPOIS)
    if resto == posicao or not resto.isdigit() or len(resto) > 18:
        return None
    return int(resto)


def _ordem_global(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Todas as plataformas (ativas e inativas) pela ordem do check-in e do painel."""
    return conn.execute("SELECT id, categoria, ativa FROM plataformas ORDER BY ordem, id").fetchall()


def opcoes_posicao(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Plataformas ativas pela ordem do ecrã, para a lista "Posição" (o ecrã filtra pela categoria)."""
    return conn.execute(
        "SELECT id, nome, categoria FROM plataformas WHERE ativa = 1 ORDER BY ordem, id"
    ).fetchall()


def posicao_atual(conn: sqlite3.Connection, plataforma_id: int) -> str:
    """Valor da lista "Posição" que descreve onde a plataforma está agora, dentro da sua categoria.

    "depois:<id>" da plataforma ativa da mesma categoria que vem antes; "inicio" se é a primeira e há outras;
    POSICAO_FIM se é a única ativa da categoria. Serve de valor inicial no formulário de edição.
    """
    todas = _ordem_global(conn)
    propria = next((p for p in todas if p["id"] == plataforma_id), None)
    if propria is None:
        return POSICAO_FIM
    anterior = None
    outras = False
    passou = False
    for p in todas:
        if p["id"] == plataforma_id:
            passou = True
            continue
        if p["ativa"] and p["categoria"] == propria["categoria"]:
            outras = True
            if not passou:
                anterior = p["id"]
    if anterior is not None:
        return f"{PREFIXO_DEPOIS}{anterior}"
    return POSICAO_INICIO if outras else POSICAO_FIM


def _posicionar(conn: sqlite3.Connection, plataforma_id: int, categoria: str, posicao: str) -> None:
    """Põe a plataforma no sítio escolhido e renumera todas (10, 20, 30…). Corre dentro da transação de quem chama.

    As outras plataformas mantêm a ordem relativa. "No início"/"no fim" contam só as ativas da categoria; se não
    houver outras, a plataforma fica onde estava (ou no fim de tudo, se for nova).
    """
    linhas = {p["id"]: p for p in _ordem_global(conn)}  # dicionário mantém a ordem global
    todas = list(linhas)
    sitio_original = todas.index(plataforma_id)
    todas.remove(plataforma_id)
    membros = [i for i in todas if linhas[i]["ativa"] and linhas[i]["categoria"] == categoria]

    alvo = _id_depois(posicao)
    if alvo is not None:
        if alvo not in membros:
            raise PosicaoInvalida(
                "A plataforma escolhida em Posição não é uma plataforma ativa desta categoria; escolhe outra posição"
            )
        indice = todas.index(alvo) + 1
    elif posicao == POSICAO_INICIO and membros:
        indice = todas.index(membros[0])
    elif membros:  # no fim da categoria (ou "no início" sem outras: dá no mesmo)
        indice = todas.index(membros[-1]) + 1
    else:
        indice = sitio_original
    todas.insert(indice, plataforma_id)
    conn.executemany(
        "UPDATE plataformas SET ordem = ? WHERE id = ?",
        [((n + 1) * PASSO_ORDEM, i) for n, i in enumerate(todas)],
    )


def _nome_repetido(conn: sqlite3.Connection, nome: str, exceto: int | None) -> bool:
    linha = conn.execute("SELECT id FROM plataformas WHERE nome = ? COLLATE NOCASE", (nome,)).fetchone()
    return linha is not None and linha["id"] != exceto


def _gravar_desafio(conn: sqlite3.Connection, plataforma_id: int, inicio: date | None) -> None:
    conn.execute("DELETE FROM planos WHERE plataforma_id = ? AND tipo = ?", (plataforma_id, planos.TIPO_DESAFIO_52))
    if inicio is not None:
        conn.execute(
            "INSERT INTO planos (plataforma_id, tipo, data_inicio) VALUES (?, ?, ?)",
            (plataforma_id, planos.TIPO_DESAFIO_52, inicio.isoformat()),
        )


def _valores(d: Dados) -> tuple:
    return (d.nome, d.categoria, d.titular, d.finalidade, d.plano_mensal_cent,
            int(d.calcula_ganho), int(d.entra_alocacao))


def criar(conn: sqlite3.Connection, d: Dados) -> int:
    """Cria uma plataforma ativa na posição escolhida. ValueError se o nome já existir; PosicaoInvalida se a
    posição não servir (nada fica gravado)."""
    if _nome_repetido(conn, d.nome, None):
        raise ValueError(f"Já existe uma plataforma chamada {d.nome!r}")
    with conn:
        cur = conn.execute(
            """INSERT INTO plataformas (nome, categoria, titular, finalidade, plano_mensal_cent,
                                        calcula_ganho, entra_alocacao, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?,
                       (SELECT COALESCE(MAX(ordem), 0) + 1 FROM plataformas))""",
            _valores(d),
        )
        _posicionar(conn, cur.lastrowid, d.categoria, d.posicao)
        _gravar_desafio(conn, cur.lastrowid, d.desafio_inicio)
    return cur.lastrowid


def atualizar(conn: sqlite3.Connection, plataforma_id: int, d: Dados) -> None:
    """Atualiza os dados (não mexe no estado ativa/inativa nem nos registos).

    Se a categoria não muda e a posição é a mesma que a plataforma já tem, ela não sai do sítio.
    """
    if _nome_repetido(conn, d.nome, plataforma_id):
        raise ValueError(f"Já existe uma plataforma chamada {d.nome!r}")
    with conn:
        antes = conn.execute("SELECT categoria FROM plataformas WHERE id = ?", (plataforma_id,)).fetchone()
        if antes is None:
            raise LookupError("Plataforma inexistente")
        mover = antes["categoria"] != d.categoria or d.posicao != posicao_atual(conn, plataforma_id)
        conn.execute(
            """UPDATE plataformas SET nome = ?, categoria = ?, titular = ?, finalidade = ?,
                   plano_mensal_cent = ?, calcula_ganho = ?, entra_alocacao = ?
               WHERE id = ?""",
            (*_valores(d), plataforma_id),
        )
        if mover:
            _posicionar(conn, plataforma_id, d.categoria, d.posicao)
        _gravar_desafio(conn, plataforma_id, d.desafio_inicio)


def desativar(conn: sqlite3.Connection, plataforma_id: int) -> None:
    """Deixa de aparecer no check-in e nos cartões; o histórico fica.

    ValueError se o último registo tiver saldo diferente de 0: o dinheiro sumiria do património sem
    nenhum registo a explicá-lo.
    """
    with conn:
        ultimo = ultimo_saldo(conn, plataforma_id)
        if ultimo is not None and ultimo["saldo_cent"] != 0:
            raise ValueError(
                f"O último registo ({calc.formatar_mes(ultimo['mes'])}) tem saldo diferente de 0. Para fechar a conta, grava no "
                "check-in o saldo 0 com o levantamento como aporte negativo (e o mesmo valor como aporte na "
                "plataforma de destino); depois desativa-a."
            )
        cur = conn.execute("UPDATE plataformas SET ativa = 0 WHERE id = ? AND ativa = 1", (plataforma_id,))
        if cur.rowcount == 0:
            raise LookupError("Plataforma inexistente ou já inativa")


def ultimo_saldo(conn: sqlite3.Connection, plataforma_id: int) -> sqlite3.Row | None:
    """(mes, saldo_cent) do último registo, para explicar no ecrã até quando a plataforma conta."""
    return conn.execute(
        "SELECT mes, saldo_cent FROM registos_mensais WHERE plataforma_id = ? ORDER BY mes DESC LIMIT 1",
        (plataforma_id,),
    ).fetchone()


def reativar(conn: sqlite3.Connection, plataforma_id: int) -> None:
    with conn:
        if conn.execute("UPDATE plataformas SET ativa = 1 WHERE id = ?", (plataforma_id,)).rowcount == 0:
            raise LookupError("Plataforma inexistente")


def apagar(conn: sqlite3.Connection, plataforma_id: int) -> None:
    """Apaga uma plataforma sem registos. ValueError se tiver registos (desativa-a em vez disso)."""
    with conn:
        n = conn.execute("SELECT COUNT(*) FROM registos_mensais WHERE plataforma_id = ?", (plataforma_id,)).fetchone()[0]
        if n:
            raise ValueError("Tem registos: não se apaga, desativa-se (o histórico fica)")
        if conn.execute("DELETE FROM plataformas WHERE id = ?", (plataforma_id,)).rowcount == 0:
            raise LookupError("Plataforma inexistente")
