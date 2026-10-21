"""Restauro do PWM a partir de uma cópia CSV: cria uma base de dados NOVA ao lado da atual.

Nunca toca na base de dados em uso e nunca sobrescreve um ficheiro existente: um restauro
que apaga o estado atual é a pior forma de falhar quando já há um problema. Para passar
a usar a restaurada, aponta a aplicação para ela (variável PWM_DB) ou, depois de fechada
a app, troca os ficheiros à mão.

Executar:
    python -m app.restauro                       # usa a cópia mais recente
    python -m app.restauro 2026-10-13_204512     # uma cópia específica (nome ou caminho)
    python -m app.restauro --destino C:\\caminho\\novo.db
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from app import backup, db

# Colunas acrescentadas ao fim de uma tabela em versões posteriores do esquema: as cópias antigas não as
# têm e continuam a restaurar-se (ficam NULL). Qualquer outra coluna em falta continua a ser erro.
COLUNAS_OPCIONAIS = {"registos_mensais": ("data_leitura",)}
# Tabelas acrescentadas em versões posteriores: uma cópia antiga sem o CSV restaura-se com a tabela vazia.
# `categorias` (v5): uma cópia antiga sem o CSV fica com as categorias de origem, as únicas que existiam até à v4.
TABELAS_OPCIONAIS = ("categorias", "configuracao", "depositos_desafio")


def ultima_copia(pasta_base: Path) -> Path:
    """A pasta de cópia mais recente (o nome AAAA-MM-DD_HHMMSS ordena como texto)."""
    copias = backup.listar_copias(pasta_base)
    if not copias:
        raise FileNotFoundError(f"Não há cópias de segurança em {pasta_base}")
    return copias[-1]


def destino_por_defeito(agora: datetime | None = None) -> Path:
    agora = agora or datetime.now()
    return db.caminho_por_defeito().parent / f"pwm_restauro_{agora.strftime('%Y-%m-%d_%H%M%S')}.db"


def _carregar_tabela(conn: sqlite3.Connection, tabela: str, ficheiro: Path) -> int:
    if not ficheiro.is_file():
        if tabela in TABELAS_OPCIONAIS:
            return 0
        raise FileNotFoundError(f"Falta o ficheiro {ficheiro.name} na cópia")
    colunas = [(r["name"], r["type"].upper()) for r in conn.execute(f"PRAGMA table_info({tabela})")]
    nomes = [c[0] for c in colunas]

    with open(ficheiro, newline="", encoding="utf-8-sig") as f:
        leitor = csv.reader(f, delimiter=";")
        cabecalho = next(leitor, None)
        if cabecalho != nomes:
            em_falta = nomes[len(cabecalho):] if cabecalho else []
            antiga = (
                bool(cabecalho)
                and cabecalho == nomes[: len(cabecalho)]
                and set(em_falta) <= set(COLUNAS_OPCIONAIS.get(tabela, ()))
            )
            if not antiga:
                raise ValueError(f"{ficheiro.name}: colunas {cabecalho} diferentes das esperadas {nomes}")
            colunas, nomes = colunas[: len(cabecalho)], cabecalho  # cópia anterior à coluna opcional
        linhas = []
        for n, linha in enumerate(leitor, start=2):
            if not linha:
                continue
            if len(linha) != len(nomes):
                raise ValueError(f"{ficheiro.name} linha {n}: {len(linha)} colunas, esperadas {len(nomes)}")
            valores = []
            for (nome, tipo), texto in zip(colunas, linha):
                if texto == "":
                    valores.append(None)
                elif tipo == "INTEGER":
                    try:  # o SQLite aceitaria texto numa coluna INTEGER sem protestar
                        inteiro = int(texto)
                    except ValueError:
                        raise ValueError(f"{ficheiro.name} linha {n}: '{texto}' não é inteiro ({nome})") from None
                    if not -(2**63) <= inteiro < 2**63:  # senão OverflowError, fora dos erros tratados no main
                        raise ValueError(f"{ficheiro.name} linha {n}: '{texto}' fora do intervalo do SQLite ({nome})")
                    valores.append(inteiro)
                else:
                    valores.append(texto)
            linhas.append(valores)

    conn.executemany(
        f"INSERT INTO {tabela} ({', '.join(nomes)}) VALUES ({', '.join('?' * len(nomes))})", linhas
    )
    return len(linhas)


def restaurar(pasta_copia: Path, destino: Path) -> dict[str, int]:
    """Cria `destino` do zero a partir dos CSV. Se algo falhar, não fica ficheiro nenhum."""
    if destino.exists():
        raise FileExistsError(f"Já existe {destino}: o restauro nunca sobrescreve")
    if not pasta_copia.is_dir():
        raise FileNotFoundError(f"Cópia inexistente: {pasta_copia}")

    conn = db.connect(destino)  # aplica também a regra de recusar caminhos dentro do OneDrive
    contagens: dict[str, int] = {}
    falhou = True
    try:
        db.init_db(conn)
        with conn:  # tudo numa transação
            if (pasta_copia / "categorias.csv").is_file():
                # A base nova nasce com as categorias de origem; a cópia traz as suas (com nomes e cores editados).
                conn.execute("DELETE FROM categorias")
            for tabela in backup.TABELAS:
                contagens[tabela] = _carregar_tabela(conn, tabela, pasta_copia / f"{tabela}.csv")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("integrity_check falhou na base restaurada")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign_key_check falhou na base restaurada")
        falhou = False
    finally:
        conn.close()
        if falhou:
            destino.unlink(missing_ok=True)
    return contagens


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Restaura o PWM para uma base de dados nova.")
    ap.add_argument("copia", nargs="?", help="nome da pasta de cópia ou caminho (por defeito, a mais recente)")
    ap.add_argument("--destino", type=Path, help="ficheiro .db a criar (por defeito, ao lado da base atual)")
    args = ap.parse_args(argv)

    base = backup.pasta_backup_por_defeito()
    try:
        if args.copia is None:
            copia = ultima_copia(base)
        else:
            copia = Path(args.copia)
            if not copia.is_absolute() and not copia.exists():
                copia = base / args.copia
        destino = args.destino or destino_por_defeito()
        contagens = restaurar(copia, destino)
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"Restauro falhou: {exc}")
        return 1

    print(f"Restaurado de {copia}")
    for tabela, n in contagens.items():
        print(f"  {tabela}: {n} linhas")
    print(f"Base nova (a atual não foi tocada): {destino}")
    print(f'Para a abrir na app:  $env:PWM_DB = "{destino}"  e depois arrancar a app nessa janela.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
