"""Dados de demonstração (fictícios) para experimentar o PWM sem dados pessoais.

Usa SEMPRE uma base de dados e uma pasta de cópias à parte: defina PWM_DB e PWM_BACKUP antes de
executar, para nunca misturar a demonstração com dados e cópias reais. Só carrega numa base vazia.

    $env:PWM_DB = "$env:LOCALAPPDATA\\pwm\\demo.db"
    $env:PWM_BACKUP = "$env:LOCALAPPDATA\\pwm\\demo-backup"
    python -m scripts.seed_demo
    python -m uvicorn app.main:app

(Na mesma janela do PowerShell, para a aplicação abrir a mesma base de demonstração. No fim:
Remove-Item Env:PWM_DB, Env:PWM_BACKUP)
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date

from app import checkin, db, planos

# nome, categoria, titular, plano mensal (€), calcula ganho, entra na alocação
PLATAFORMAS = [
    ("Conta Corrente", "conta_corrente", "Conjunto", 0, 0, 0),
    ("Conta Trânsito", "transito", "Ana", 0, 0, 0),
    ("Fundo de Liberdade", "emergencia", "Conjunto", 0, 1, 0),
    ("Conta Viagens", "viagens", "Ana", 20, 1, 0),
    ("Plataforma P2P", "p2p", "Ana", 0, 1, 0),
    ("Corretora ETF A", "investimento", "Ana", 50, 1, 1),
    ("Corretora ETF B", "investimento", "Rui", 50, 1, 1),
    ("Certificados de Poupança", "poupanca", "Ana", 0, 1, 1),
    ("PPR Exemplo A", "reforma", "Ana", 50, 1, 1),
    ("PPR Exemplo B", "reforma", "Rui", 50, 1, 1),
    ("Numerário em casa", "numerario", "Conjunto", 0, 0, 0),
]

NOME_P2P = "Plataforma P2P"  # tem o Desafio das 52 semanas
INICIO_DESAFIO = "2024-01-01"

LEITURAS = [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]

# Plataformas com ganho: saldo inicial (€) e rendimento mensal fictício.
INICIAL_EUR = {
    "Fundo de Liberdade": 3000,
    "Conta Viagens": 150,
    "Plataforma P2P": 1200,
    "Corretora ETF A": 2500,
    "Corretora ETF B": 1800,
    "Certificados de Poupança": 5000,
    "PPR Exemplo A": 4000,
    "PPR Exemplo B": 3500,
}
TAXA_MENSAL = {
    "Fundo de Liberdade": 0.002,
    "Conta Viagens": 0.001,
    "Plataforma P2P": 0.005,
    "Corretora ETF A": 0.006,
    "Corretora ETF B": 0.004,
    "Certificados de Poupança": 0.002,
    "PPR Exemplo A": 0.005,
    "PPR Exemplo B": 0.003,
}

# Plataformas só de saldo: um saldo (€) por leitura.
SO_SALDO_EUR = {
    "Conta Corrente": [2310, 2185, 2420],
    "Conta Trânsito": [100, 100, 100],
    "Numerário em casa": [150, 150, 150],
}


def carregar(conn: sqlite3.Connection) -> None:
    """Insere plataformas, o plano do Desafio e três meses de registos fictícios (tudo numa transação)."""
    with conn:
        for ordem, (nome, cat, titular, plano_eur, ganho, aloc) in enumerate(PLATAFORMAS, start=1):
            conn.execute(
                """INSERT INTO plataformas
                   (nome, categoria, titular, plano_mensal_cent, calcula_ganho, entra_alocacao, ordem)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (nome, cat, titular, plano_eur * 100, ganho, aloc, ordem),
            )
        p2p = conn.execute("SELECT id FROM plataformas WHERE nome = ?", (NOME_P2P,)).fetchone()
        conn.execute(
            "INSERT INTO planos (plataforma_id, tipo, data_inicio) VALUES (?, ?, ?)",
            (p2p["id"], planos.TIPO_DESAFIO_52, INICIO_DESAFIO),
        )
        inicio = date.fromisoformat(INICIO_DESAFIO)

        for p in conn.execute("SELECT id, nome, plano_mensal_cent, calcula_ganho FROM plataformas").fetchall():
            if p["calcula_ganho"]:
                saldo = INICIAL_EUR[p["nome"]] * 100
                for i, leitura in enumerate(LEITURAS):
                    if i == 0:
                        aporte = 0  # saldo inicial: sem ganho
                    else:
                        if p["nome"] == NOME_P2P:
                            aporte = planos.sugerir_desafio(LEITURAS[i - 1], leitura, inicio).total_cent
                        else:
                            aporte = p["plano_mensal_cent"]
                        saldo = round((saldo + aporte) * (1 + TAXA_MENSAL[p["nome"]]))
                    conn.execute(
                        """INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura)
                           VALUES (?, ?, ?, ?, ?)""",
                        (p["id"], checkin.mes_de(leitura), saldo, aporte, leitura.isoformat()),
                    )
            else:
                for leitura, saldo_eur in zip(LEITURAS, SO_SALDO_EUR[p["nome"]]):
                    conn.execute(
                        """INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura)
                           VALUES (?, ?, ?, 0, NULL)""",
                        (p["id"], checkin.mes_de(leitura), saldo_eur * 100),
                    )


def main() -> int:
    em_falta = [v for v in ("PWM_DB", "PWM_BACKUP") if not os.environ.get(v)]
    if em_falta:
        print(
            f"Recusado: defina {' e '.join(em_falta)} para uma base e uma pasta de cópias de demonstração à parte, "
            "para não misturar com os dados reais.\n"
            '  $env:PWM_DB = "$env:LOCALAPPDATA\\pwm\\demo.db"\n'
            '  $env:PWM_BACKUP = "$env:LOCALAPPDATA\\pwm\\demo-backup"'
        )
        return 1
    conn = db.connect()
    try:
        db.init_db(conn)
        if conn.execute("SELECT COUNT(*) FROM plataformas").fetchone()[0]:
            print(f"Recusado: {db.caminho_por_defeito()} já tem plataformas. A demonstração só carrega numa base vazia.")
            return 1
        carregar(conn)
    finally:
        conn.close()
    print(f"Demonstração carregada em {db.caminho_por_defeito()}")
    print("Abra a aplicação nesta mesma janela: python -m uvicorn app.main:app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
