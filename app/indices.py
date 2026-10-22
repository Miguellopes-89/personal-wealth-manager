"""Índices de referência (esquema v6): gestão dos índices e dos seus valores mensais.

Lógica sem web, como em `categorias.py`. Regras:
- Um índice é qualquer série de valores que se queira comparar com o património: o nível de um índice de
  mercado, o preço de um ETF de acumulação (já inclui dividendos e custos) ou o índice de preços (inflação).
  Só as variações contam, por isso a base do índice é indiferente.
- Cada índice compara-se com um perímetro: uma categoria (ex.: investimento) ou o património todo (NULL).
- O valor escreve-se no check-in, no dia da leitura dos saldos (ou o último publicado, no caso da inflação,
  que sai com atraso: o desfasamento é constante, por isso as variações continuam comparáveis).
- Valores guardados como inteiros em décimas de milésima (ESCALA): 130,145 -> 1 301 450. Mais de 4 casas
  decimais arredondam.
- Nomes iguais sem contar maiúsculas nem acentos recusados (como nas categorias).
- Só se apaga um índice sem valores; com valores, desativa-se (sai do check-in e do painel, os valores ficam).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app import calc
from app.categorias import _chave

ESCALA = 10_000  # 4 casas decimais
LIMITE_VALOR = 10**9 * ESCALA  # mil milhões: muito acima de qualquer índice, muito abaixo do INTEGER do SQLite
LIMITE_NOME = 40
PERIMETRO_TOTAL = ""  # no formulário: o património todo (na base, NULL)


@dataclass(frozen=True)
class Indice:
    id: int
    nome: str
    perimetro: str | None  # código da categoria; None = património todo
    ativo: bool
    ordem: int
    n_valores: int = 0


def valor_de_texto(texto: str) -> int:
    """'130,145' -> 1301450. Levanta ValueError se for inválido, zero ou negativo."""
    valor = calc.texto_para_decimal(texto)
    inteiro = int((valor * ESCALA).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if inteiro <= 0:
        raise ValueError("O valor do índice tem de ser maior que zero")
    if inteiro > LIMITE_VALOR:
        raise ValueError(f"Valor fora do intervalo aceite: {texto!r}")
    return inteiro


def valor_para_texto(valor: int) -> str:
    """1301450 -> '130,145'; 1000000 -> '100' (sem zeros à direita; serve de valor inicial de um campo)."""
    inteiro, resto = divmod(valor, ESCALA)
    decimais = f"{resto:04d}".rstrip("0")
    return f"{inteiro},{decimais}" if decimais else str(inteiro)


def listar(conn: sqlite3.Connection, so_ativos: bool = False) -> list[Indice]:
    sql = """SELECT i.id, i.nome, i.perimetro, i.ativo, i.ordem, COUNT(v.mes) AS n
             FROM indices i LEFT JOIN valores_indice v ON v.indice_id = i.id"""
    if so_ativos:
        sql += " WHERE i.ativo = 1"
    sql += " GROUP BY i.id ORDER BY i.ordem, i.id"
    return [Indice(r["id"], r["nome"], r["perimetro"], bool(r["ativo"]), r["ordem"], r["n"]) for r in conn.execute(sql)]


def obter(conn: sqlite3.Connection, indice_id: int) -> Indice | None:
    return next((i for i in listar(conn) if i.id == indice_id), None)


def _validar(conn: sqlite3.Connection, nome: str, perimetro: str | None, exceto: int | None) -> tuple[str, str | None]:
    nome = " ".join((nome or "").split())
    if not nome:
        raise ValueError("Indica o nome do índice")
    if len(nome) > LIMITE_NOME:
        raise ValueError(f"O nome tem no máximo {LIMITE_NOME} caracteres")
    if not _chave(nome):
        raise ValueError("O nome tem de ter pelo menos uma letra ou um número")
    for i in listar(conn):
        if i.id != exceto and _chave(i.nome) == _chave(nome):
            raise ValueError(f"Já existe o índice {i.nome!r}")
    perimetro = (perimetro or "").strip() or None
    if perimetro is not None and conn.execute(
        "SELECT 1 FROM categorias WHERE codigo = ?", (perimetro,)
    ).fetchone() is None:
        raise ValueError("Categoria inexistente")
    return nome, perimetro


def criar(conn: sqlite3.Connection, nome: str, perimetro: str | None) -> int:
    """Cria o índice no fim da lista e devolve o id. ValueError se o nome ou o perímetro forem inválidos."""
    nome, perimetro = _validar(conn, nome, perimetro, None)
    ordem = (conn.execute("SELECT MAX(ordem) FROM indices").fetchone()[0] or 0) + 10
    with conn:
        cur = conn.execute("INSERT INTO indices (nome, perimetro, ordem) VALUES (?, ?, ?)", (nome, perimetro, ordem))
    return cur.lastrowid


def editar(conn: sqlite3.Connection, indice_id: int, nome: str, perimetro: str | None) -> None:
    """Muda o nome e o perímetro (a comparação passada passa a usar o perímetro novo). LookupError se não existir."""
    if obter(conn, indice_id) is None:
        raise LookupError("Índice inexistente")
    nome, perimetro = _validar(conn, nome, perimetro, indice_id)
    with conn:
        conn.execute("UPDATE indices SET nome = ?, perimetro = ? WHERE id = ?", (nome, perimetro, indice_id))


def definir_ativo(conn: sqlite3.Connection, indice_id: int, ativo: bool) -> None:
    with conn:
        if conn.execute("UPDATE indices SET ativo = ? WHERE id = ?", (int(ativo), indice_id)).rowcount == 0:
            raise LookupError("Índice inexistente")


def apagar(conn: sqlite3.Connection, indice_id: int) -> None:
    """Apaga um índice sem valores. Com valores, ValueError (desativar guarda o histórico)."""
    indice = obter(conn, indice_id)
    if indice is None:
        raise LookupError("Índice inexistente")
    if indice.n_valores:
        raise ValueError(
            f"{indice.nome!r} tem {indice.n_valores} valor(es) gravado(s): desativa-o para o tirar do check-in "
            "e do painel sem perder o histórico"
        )
    with conn:
        conn.execute("DELETE FROM indices WHERE id = ?", (indice_id,))


def valores(conn: sqlite3.Connection, indice_id: int) -> dict[str, int]:
    """mês -> valor, por ordem de mês."""
    return {
        r["mes"]: r["valor"]
        for r in conn.execute("SELECT mes, valor FROM valores_indice WHERE indice_id = ? ORDER BY mes", (indice_id,))
    }


def valores_do_mes(conn: sqlite3.Connection, mes: str) -> dict[int, int]:
    """indice_id -> valor gravado nesse mês."""
    return {r["indice_id"]: r["valor"] for r in conn.execute("SELECT indice_id, valor FROM valores_indice WHERE mes = ?", (mes,))}


def validar_valores(conn: sqlite3.Connection, textos: dict[int, str]) -> tuple[dict[int, int], dict[int, str]]:
    """Textos do check-in -> (valores a gravar, erros). Em branco = não mexer. Só índices ativos."""
    ativos = {i.id for i in listar(conn, so_ativos=True)}
    a_gravar: dict[int, int] = {}
    erros: dict[int, str] = {}
    for indice_id, texto in textos.items():
        if indice_id not in ativos:
            erros[indice_id] = "Índice desconhecido ou inativo"
        elif (texto or "").strip():
            try:
                a_gravar[indice_id] = valor_de_texto(texto)
            except ValueError as exc:
                erros[indice_id] = str(exc)
    return a_gravar, erros


def gravar_valores(conn: sqlite3.Connection, mes: str, a_gravar: dict[int, int]) -> None:
    """Grava (ou substitui) os valores do mês. Não abre transação: corre dentro da do check-in."""
    conn.executemany(
        """INSERT INTO valores_indice (indice_id, mes, valor) VALUES (?, ?, ?)
           ON CONFLICT (indice_id, mes) DO UPDATE SET valor = excluded.valor""",
        [(i, mes, v) for i, v in a_gravar.items()],
    )


def apagar_valor(conn: sqlite3.Connection, indice_id: int, mes: str) -> None:
    with conn:
        if conn.execute("DELETE FROM valores_indice WHERE indice_id = ? AND mes = ?", (indice_id, mes)).rowcount == 0:
            raise LookupError("Valor inexistente")
