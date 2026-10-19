"""Valores de configuração editáveis na aplicação (tabela `configuracao`).

Por agora só a despesa mensal de referência, que serve para a cobertura do fundo de liberdade.
Fica na base de dados (e não no código) porque é um dado pessoal: o repositório público não o tem,
e entra nas cópias de segurança como o resto.
"""
from __future__ import annotations

import sqlite3

from app import calc

DESPESA_MENSAL = "despesa_mensal_cent"


def obter_despesa_mensal(conn: sqlite3.Connection) -> int | None:
    """Despesa mensal de referência em cêntimos; None se ainda não foi definida."""
    linha = conn.execute("SELECT valor FROM configuracao WHERE chave = ?", (DESPESA_MENSAL,)).fetchone()
    return linha["valor"] if linha else None


def validar_despesa_mensal(texto: str) -> int | None:
    """Texto do formulário -> cêntimos. Em branco = apagar a referência (None). Levanta ValueError."""
    if not (texto or "").strip():
        return None
    cent = calc.euros_para_cent(texto)
    if cent <= 0:
        raise ValueError("A despesa mensal tem de ser maior que zero")
    return cent


def definir_despesa_mensal(conn: sqlite3.Connection, cent: int | None) -> None:
    """Grava (ou apaga, com None) a despesa mensal de referência."""
    if cent is not None and cent <= 0:
        raise ValueError("A despesa mensal tem de ser maior que zero")
    with conn:
        if cent is None:
            conn.execute("DELETE FROM configuracao WHERE chave = ?", (DESPESA_MENSAL,))
        else:
            conn.execute(
                "INSERT INTO configuracao (chave, valor) VALUES (?, ?) "
                "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
                (DESPESA_MENSAL, cent),
            )
