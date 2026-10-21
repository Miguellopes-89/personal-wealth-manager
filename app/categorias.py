"""Categorias das plataformas (esquema v5): listar, criar, renomear e apagar.

Lógica sem web, como em `plataformas.py`. Regras:
- O código é interno e nunca muda: renomear só muda o nome no ecrã, por isso o histórico e o painel não mexem.
- O código de uma categoria nova vem do nome ("Rendimento extra" -> "rendimento_extra").
- Não há dois nomes iguais sem contar maiúsculas nem acentos: "poupanca" bate com "Poupança". Assim o painel
  não divide o mesmo dinheiro em duas categorias por causa de uma letra.
- Só se apaga uma categoria sem plataformas (nem inativas). O "Fundo de liberdade" (`emergencia`) nunca se
  apaga: é a base da cobertura em meses do painel.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

CATEGORIA_FUNDO = "emergencia"  # código interno; no ecrã, por defeito, "Fundo de liberdade"
PROTEGIDAS = frozenset({CATEGORIA_FUNDO})
LIMITE_NOME = 40

# Cores para as categorias novas, distintas das de origem (ver db.CATEGORIAS_BASE). Escolhe-se a primeira
# ainda livre; esgotadas, repetem-se pela ordem.
CORES_NOVAS = ("#1f9e89", "#c94f4f", "#6b8e23", "#8e6bbf", "#d4a017", "#4682b4", "#b5651d", "#708090")


@dataclass(frozen=True)
class Categoria:
    codigo: str
    nome: str
    cor: str
    ordem: int
    n_plataformas: int = 0

    @property
    def protegida(self) -> bool:
        return self.codigo in PROTEGIDAS


def _chave(texto: str) -> str:
    """Forma comparável de um nome: sem acentos, minúsculas, só letras e números separados por '_'."""
    sem_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", sem_acentos.lower()).strip("_")


def listar(conn: sqlite3.Connection) -> list[Categoria]:
    """Todas as categorias pela ordem do ecrã, com o número de plataformas (ativas e inativas)."""
    return [
        Categoria(r["codigo"], r["nome"], r["cor"], r["ordem"], r["n"])
        for r in conn.execute(
            """SELECT c.codigo, c.nome, c.cor, c.ordem, COUNT(p.id) AS n
               FROM categorias c LEFT JOIN plataformas p ON p.categoria = c.codigo
               GROUP BY c.codigo ORDER BY c.ordem, c.nome"""
        )
    ]


def codigos(conn: sqlite3.Connection) -> list[str]:
    return [c.codigo for c in listar(conn)]


def rotulos(conn: sqlite3.Connection) -> dict[str, str]:
    """código -> nome no ecrã, pela ordem do ecrã."""
    return {c.codigo: c.nome for c in listar(conn)}


def _validar_nome(conn: sqlite3.Connection, nome: str, exceto: str | None) -> str:
    nome = " ".join((nome or "").split())  # tira espaços a mais (também no meio)
    if not nome:
        raise ValueError("Indica o nome da categoria")
    if len(nome) > LIMITE_NOME:
        raise ValueError(f"O nome tem no máximo {LIMITE_NOME} caracteres")
    if not _chave(nome):
        raise ValueError("O nome tem de ter pelo menos uma letra ou um número")
    for c in listar(conn):
        if c.codigo != exceto and _chave(c.nome) == _chave(nome):
            raise ValueError(f"Já existe a categoria {c.nome!r}")
    return nome


def criar(conn: sqlite3.Connection, nome: str) -> str:
    """Cria a categoria no fim da lista e devolve o código. ValueError se o nome for inválido ou repetido."""
    nome = _validar_nome(conn, nome, None)
    existentes = listar(conn)
    base = _chave(nome)[:30].strip("_")
    usados = {c.codigo for c in existentes}
    codigo, n = base, 2
    while codigo in usados:  # um código antigo pode ter ficado de uma categoria renomeada
        codigo, n = f"{base}_{n}", n + 1
    cores_usadas = {c.cor for c in existentes}
    cor = next((c for c in CORES_NOVAS if c not in cores_usadas), CORES_NOVAS[len(existentes) % len(CORES_NOVAS)])
    ordem = max((c.ordem for c in existentes), default=0) + 1
    with conn:
        conn.execute("INSERT INTO categorias (codigo, nome, cor, ordem) VALUES (?, ?, ?, ?)", (codigo, nome, cor, ordem))
    return codigo


def renomear(conn: sqlite3.Connection, codigo: str, nome: str) -> None:
    """Muda só o nome no ecrã. LookupError se não existir; ValueError se o nome for inválido ou repetido."""
    nome = _validar_nome(conn, nome, codigo)
    with conn:
        if conn.execute("UPDATE categorias SET nome = ? WHERE codigo = ?", (nome, codigo)).rowcount == 0:
            raise LookupError("Categoria inexistente")


def apagar(conn: sqlite3.Connection, codigo: str) -> None:
    """Apaga uma categoria sem plataformas. ValueError se estiver protegida ou em uso."""
    categoria = next((c for c in listar(conn) if c.codigo == codigo), None)
    if categoria is None:
        raise LookupError("Categoria inexistente")
    if categoria.protegida:
        raise ValueError(f"{categoria.nome!r} não se apaga: é a base da cobertura do fundo de liberdade no painel")
    if categoria.n_plataformas:
        raise ValueError(
            f"{categoria.nome!r} tem {categoria.n_plataformas} plataforma(s): muda-lhes a categoria antes de a apagar"
        )
    with conn:
        conn.execute("DELETE FROM categorias WHERE codigo = ?", (codigo,))
