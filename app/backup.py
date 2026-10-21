"""Cópia de segurança do PWM: exporta as tabelas para CSV com data e hora.

Cada exportação cria uma pasta nova (AAAA-MM-DD_HHMMSS) e nunca sobrescreve a anterior:
se um erro de registo contaminar o último estado, as cópias antigas continuam boas.
Os CSV usam ';' e UTF-8 com BOM para abrirem direto no Excel em português.

Executar: python -m app.backup
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from app import db

# Ordem de carga no restauro (plataformas antes das tabelas que as referem). Um teste garante que a lista
# cobre todas as tabelas do esquema: uma tabela nova esquecida aqui ficava fora das cópias.
TABELAS = ("plataformas", "registos_mensais", "planos", "configuracao", "depositos_desafio")
PADRAO_PASTA = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
_PADRAO_TEMPORARIA = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}\.tmp$")
TENTATIVAS_RENOMEAR = 5  # o OneDrive (ou um antivírus) pode prender a pasta acabada de escrever


def pasta_backup_por_defeito() -> Path:
    env = os.environ.get("PWM_BACKUP")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "backup"


def listar_copias(pasta_base: Path) -> list[Path]:
    """Cópias existentes (só pastas com o padrão de nome), da mais antiga para a mais recente."""
    if not pasta_base.is_dir():
        return []
    return sorted(p for p in pasta_base.iterdir() if p.is_dir() and PADRAO_PASTA.match(p.name))


def _renomear(origem: Path, destino: Path, tentativas: int = TENTATIVAS_RENOMEAR, pausa: float = 0.2) -> None:
    for n in range(tentativas):
        try:
            origem.rename(destino)
            return
        except PermissionError:
            if n == tentativas - 1:
                raise
            time.sleep(pausa)


def _conteudo(conn: sqlite3.Connection) -> dict[str, bytes]:
    """O CSV de cada tabela já em bytes (UTF-8 com BOM): serve para comparar com a última cópia e para gravar."""
    saida: dict[str, bytes] = {}
    for tabela in TABELAS:  # nomes fixos acima, nunca vindos de input
        cur = conn.execute(f"SELECT * FROM {tabela}")
        buf = io.StringIO(newline="")
        escritor = csv.writer(buf, delimiter=";")
        escritor.writerow([c[0] for c in cur.description])
        escritor.writerows(cur)
        saida[tabela] = buf.getvalue().encode("utf-8-sig")
    return saida


def _igual(pasta: Path, conteudo: dict[str, bytes]) -> bool:
    for tabela, dados in conteudo.items():
        ficheiro = pasta / f"{tabela}.csv"
        if not ficheiro.is_file() or ficheiro.read_bytes() != dados:
            return False
    return True


def exportar_csv(
    conn: sqlite3.Connection,
    pasta_base: Path,
    agora: datetime | None = None,
    manter: int = 30,
) -> Path:
    """Exporta as tabelas para uma pasta nova; se nada mudou desde a última cópia, devolve essa.

    Apaga as cópias mais antigas além de `manter`, exceto a última de cada mês.
    """
    if manter < 1:
        raise ValueError("manter tem de ser >= 1")
    agora = agora or datetime.now()
    conteudo = _conteudo(conn)
    copias = listar_copias(pasta_base)
    if copias and _igual(copias[-1], conteudo):
        return copias[-1]

    nome = agora.strftime("%Y-%m-%d_%H%M%S")
    destino = pasta_base / nome
    temporaria = pasta_base / f"{nome}.tmp"
    if destino.exists():
        raise FileExistsError(f"Já existe uma cópia com este nome: {destino}")

    temporaria.mkdir(parents=True, exist_ok=True)
    try:
        for tabela, dados in conteudo.items():
            (temporaria / f"{tabela}.csv").write_bytes(dados)
        _renomear(temporaria, destino)  # só fica visível quando está completa
    except Exception:
        shutil.rmtree(temporaria, ignore_errors=True)
        raise

    _limpar_antigas(pasta_base, manter)
    return destino


def _limpar_antigas(pasta_base: Path, manter: int) -> None:
    """Apaga só pastas com o padrão de nome das cópias; a última de cada mês fica sempre.

    Também apaga pastas .tmp órfãs (de uma cópia interrompida): nunca chegaram a ser cópias completas.
    """
    for orfa in pasta_base.iterdir():
        if orfa.is_dir() and _PADRAO_TEMPORARIA.match(orfa.name):
            shutil.rmtree(orfa, ignore_errors=True)
    copias = listar_copias(pasta_base)
    protegidas = {p.name[:7]: p for p in copias}.values()  # ordenadas: fica a mais recente de cada mês
    for antiga in copias[:-manter]:
        if antiga not in protegidas:
            shutil.rmtree(antiga)


def main() -> int:
    caminho = db.caminho_por_defeito()
    if not caminho.exists():
        print(f"Ainda não há base de dados em {caminho}: nada para guardar.")
        return 1
    conn = db.connect()
    try:
        destino = exportar_csv(conn, pasta_backup_por_defeito())
    finally:
        conn.close()
    print(f"Cópia de segurança guardada em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
