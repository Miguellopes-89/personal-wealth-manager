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
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from app import calc, db, planos

LIMITE_ORDEM = 1_000_000  # a ordem só arruma a lista; um inteiro enorme rebentava no SQLite (erro 500)


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
    ordem: int
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

    ordem = 0
    texto_ordem = (form.get("ordem") or "").strip()
    if texto_ordem:
        try:
            ordem = int(texto_ordem)
        except ValueError:
            erros["ordem"] = "A ordem tem de ser um número inteiro"
        else:
            if abs(ordem) > LIMITE_ORDEM:
                erros["ordem"] = f"A ordem tem de estar entre -{LIMITE_ORDEM} e {LIMITE_ORDEM}"

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
            ordem=ordem,
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


def proxima_ordem(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COALESCE(MAX(ordem), 0) + 1 FROM plataformas").fetchone()[0]


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
            int(d.calcula_ganho), int(d.entra_alocacao), d.ordem)


def criar(conn: sqlite3.Connection, d: Dados) -> int:
    """Cria uma plataforma ativa. ValueError se o nome já existir."""
    if _nome_repetido(conn, d.nome, None):
        raise ValueError(f"Já existe uma plataforma chamada {d.nome!r}")
    with conn:
        cur = conn.execute(
            """INSERT INTO plataformas (nome, categoria, titular, finalidade, plano_mensal_cent,
                                        calcula_ganho, entra_alocacao, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            _valores(d),
        )
        _gravar_desafio(conn, cur.lastrowid, d.desafio_inicio)
    return cur.lastrowid


def atualizar(conn: sqlite3.Connection, plataforma_id: int, d: Dados) -> None:
    """Atualiza os dados (não mexe no estado ativa/inativa nem nos registos)."""
    if _nome_repetido(conn, d.nome, plataforma_id):
        raise ValueError(f"Já existe uma plataforma chamada {d.nome!r}")
    with conn:
        cur = conn.execute(
            """UPDATE plataformas SET nome = ?, categoria = ?, titular = ?, finalidade = ?,
                   plano_mensal_cent = ?, calcula_ganho = ?, entra_alocacao = ?, ordem = ?
               WHERE id = ?""",
            (*_valores(d), plataforma_id),
        )
        if cur.rowcount == 0:
            raise LookupError("Plataforma inexistente")
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
