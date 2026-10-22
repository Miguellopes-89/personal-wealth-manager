import csv
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app import backup, db, restauro

# Esquema da versão 1 (sem registos_mensais.data_leitura), como está na base real antes da migração.
ESQUEMA_V1 = """
CREATE TABLE plataformas (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL UNIQUE, categoria TEXT NOT NULL, titular TEXT NOT NULL,
    finalidade TEXT, plano_mensal_cent INTEGER NOT NULL DEFAULT 0, calcula_ganho INTEGER NOT NULL DEFAULT 1,
    entra_alocacao INTEGER NOT NULL DEFAULT 1, ativa INTEGER NOT NULL DEFAULT 1, ordem INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE registos_mensais (
    plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE RESTRICT,
    mes TEXT NOT NULL, saldo_cent INTEGER NOT NULL, aporte_cent INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (plataforma_id, mes)
) WITHOUT ROWID;
CREATE TABLE planos (
    id INTEGER PRIMARY KEY, plataforma_id INTEGER NOT NULL REFERENCES plataformas(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL, data_inicio TEXT NOT NULL
);
INSERT INTO plataformas (id, nome, categoria, titular) VALUES (1, 'Bondora Go & Grow', 'p2p', 'Miguel');
INSERT INTO registos_mensais VALUES (1, '2026-10', 500000, 0);
PRAGMA user_version = 1;
"""


def test_base_v1_migra_sem_perder_dados():
    conn = db.connect(":memory:")
    conn.executescript(ESQUEMA_V1)

    db.init_db(conn)

    linha = conn.execute("SELECT * FROM registos_mensais").fetchone()
    assert (linha["plataforma_id"], linha["mes"], linha["saldo_cent"], linha["aporte_cent"]) == (1, "2026-10", 500000, 0)
    assert linha["data_leitura"] is None  # a migração não inventa datas
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    with pytest.raises(sqlite3.IntegrityError):  # a coluna acrescentada também valida a data
        conn.execute("UPDATE registos_mensais SET data_leitura = '2026-02-30'")
    conn.execute("UPDATE registos_mensais SET data_leitura = '2026-10-13'")
    conn.close()


def test_base_v2_ganha_a_tabela_configuracao_sem_perder_dados():
    conn = db.connect(":memory:")
    conn.executescript(ESQUEMA_V1)
    conn.execute("ALTER TABLE registos_mensais ADD COLUMN data_leitura TEXT")
    conn.execute("UPDATE registos_mensais SET data_leitura = '2026-10-13'")
    conn.execute("PRAGMA user_version = 2")

    db.init_db(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM configuracao").fetchone()[0] == 0
    assert conn.execute("SELECT saldo_cent, data_leitura FROM registos_mensais").fetchone()[:] == (500000, "2026-10-13")
    conn.close()


def test_migracao_e_idempotente():
    conn = db.connect(":memory:")
    conn.executescript(ESQUEMA_V1)
    db.init_db(conn)
    conn.execute("UPDATE registos_mensais SET data_leitura = '2026-10-13'")
    db.init_db(conn)  # segunda vez: não falha nem apaga a data
    assert conn.execute("SELECT data_leitura FROM registos_mensais").fetchone()[0] == "2026-10-13"
    conn.close()


def test_base_de_versao_futura_e_recusada():
    conn = db.connect(":memory:")
    conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError, match="mais recente"):
        db.init_db(conn)
    conn.close()


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    c.execute("INSERT INTO plataformas (nome, categoria, titular) VALUES ('Degiro', 'investimento', 'Miguel')")
    yield c
    c.close()


def _inserir(conn, data):
    conn.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) "
        "VALUES (1, '2026-10', 100, 0, ?)",
        (data,),
    )


@pytest.mark.parametrize("data", ["2026-10-13", "2028-02-29", None])
def test_data_de_leitura_valida_aceite(conn, data):
    _inserir(conn, data)


@pytest.mark.parametrize(
    "mau", ["2026-02-30", "2026-13-01", "2026-10-00", "13/10/2026", "2026-10-13 10:00", "2026-1-3", "hoje", ""]
)
def test_data_de_leitura_invalida_rejeitada(conn, mau):
    with pytest.raises(sqlite3.IntegrityError):
        _inserir(conn, mau)


def _cortar_ultimas_colunas(ficheiro, n):
    with open(ficheiro, newline="", encoding="utf-8-sig") as f:
        linhas = list(csv.reader(f, delimiter=";"))
    with open(ficheiro, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows([linha[:-n] for linha in linhas])


@pytest.fixture
def copia(conn, tmp_path):
    _inserir(conn, "2026-10-13")
    conn.commit()
    return backup.exportar_csv(conn, tmp_path / "backup", agora=datetime(2026, 10, 14, 9, 0, 0))


def test_restaura_copia_anterior_a_coluna_data_leitura(copia, tmp_path):
    _cortar_ultimas_colunas(copia / "registos_mensais.csv", 1)  # como as cópias feitas na versão 1
    destino = tmp_path / "restaurada.db"

    contagens = restauro.restaurar(copia, destino)

    assert contagens["registos_mensais"] == 1
    nova = db.connect(destino)
    try:
        linha = nova.execute("SELECT saldo_cent, data_leitura FROM registos_mensais").fetchone()
        assert (linha["saldo_cent"], linha["data_leitura"]) == (100, None)
    finally:
        nova.close()


def test_coluna_obrigatoria_em_falta_continua_a_falhar(copia, tmp_path):
    _cortar_ultimas_colunas(copia / "registos_mensais.csv", 2)  # falta aporte_cent, que não é opcional
    destino = tmp_path / "restaurada.db"

    with pytest.raises(ValueError, match="colunas"):
        restauro.restaurar(copia, destino)
    assert not destino.exists()


def test_base_v3_ganha_a_tabela_depositos_desafio_sem_perder_dados():
    conn = db.connect(":memory:")
    conn.executescript(ESQUEMA_V1)
    conn.execute("ALTER TABLE registos_mensais ADD COLUMN data_leitura TEXT")
    conn.execute("UPDATE registos_mensais SET data_leitura = '2026-10-13'")
    conn.execute("CREATE TABLE configuracao (chave TEXT PRIMARY KEY, valor INTEGER NOT NULL) WITHOUT ROWID")
    conn.execute("INSERT INTO configuracao VALUES ('despesa_mensal_cent', 123400)")
    conn.execute("PRAGMA user_version = 3")

    db.init_db(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM depositos_desafio").fetchone()[0] == 0
    assert conn.execute("SELECT valor FROM configuracao").fetchone()[0] == 123400
    assert conn.execute("SELECT saldo_cent, data_leitura FROM registos_mensais").fetchone()[:] == (500000, "2026-10-13")
    conn.close()


@pytest.mark.parametrize("domingo", ["2026-10-18", "2027-01-03"])
def test_deposito_aceita_domingos(conn, domingo):
    _inserir(conn, "2026-10-13")
    conn.execute("INSERT INTO depositos_desafio VALUES (1, ?, 4200, '2026-10')", (domingo,))


@pytest.mark.parametrize("mau", ["2026-10-17", "2026-02-29", "18/10/2026", "2026-10-18 00:00", ""])
def test_deposito_recusa_datas_que_nao_sao_domingos(conn, mau):
    _inserir(conn, "2026-10-13")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO depositos_desafio VALUES (1, ?, 4200, '2026-10')", (mau,))


def test_deposito_exige_registo_do_mes_e_valor_positivo(conn):
    with pytest.raises(sqlite3.IntegrityError):  # sem registo de 2026-10
        conn.execute("INSERT INTO depositos_desafio VALUES (1, '2026-10-18', 4200, '2026-10')")
    _inserir(conn, "2026-10-13")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO depositos_desafio VALUES (1, '2026-10-18', 0, '2026-10')")


def test_restaura_copia_sem_depositos_desafio(copia, tmp_path):
    (copia / "depositos_desafio.csv").unlink()  # como as cópias feitas na versão 3
    destino = tmp_path / "restaurada.db"

    contagens = restauro.restaurar(copia, destino)

    assert contagens["depositos_desafio"] == 0
    assert contagens["registos_mensais"] == 1


def test_restaura_depositos_desafio(conn, tmp_path):
    _inserir(conn, "2026-10-13")
    conn.execute("INSERT INTO depositos_desafio VALUES (1, '2026-10-18', 4200, '2026-10')")
    conn.commit()
    pasta = backup.exportar_csv(conn, tmp_path / "backup", agora=datetime(2026, 10, 21, 9, 0, 0))
    destino = tmp_path / "restaurada.db"

    restauro.restaurar(pasta, destino)

    nova = db.connect(destino)
    try:
        assert nova.execute("SELECT * FROM depositos_desafio").fetchall()[0][:] == (1, "2026-10-18", 4200, "2026-10")
    finally:
        nova.close()


# --- Versão 4 -> 5: categorias numa tabela própria -------------------------------------------------------------

ESQUEMA_V4 = (Path(__file__).parent / "esquema_v4.sql").read_text(encoding="utf-8")
TABELAS_V4 = ("plataformas", "registos_mensais", "planos", "configuracao", "depositos_desafio")


def _base_v4(caminho):
    conn = db.connect(caminho)
    conn.executescript(ESQUEMA_V4)
    conn.executescript(
        """
        INSERT INTO plataformas (id, nome, categoria, titular, plano_mensal_cent, ordem) VALUES
            (3, 'P2P Exemplo', 'p2p', 'Ana', 0, 1), (7, 'Fundo Exemplo', 'emergencia', 'Rui', 2500, 2);
        INSERT INTO registos_mensais VALUES (3, '2026-09', 100000, 0, '2026-09-13'), (3, '2026-10', 104500, 4000, '2026-10-11'),
                                            (7, '2026-10', 300000, 2500, NULL);
        INSERT INTO planos (id, plataforma_id, tipo, data_inicio) VALUES (5, 3, 'desafio_52', '2026-01-01');
        INSERT INTO configuracao VALUES ('despesa_mensal_cent', 150000);
        INSERT INTO depositos_desafio VALUES (3, '2026-09-20', 3800, '2026-10'), (3, '2026-09-27', 3900, '2026-10');
        PRAGMA user_version = 4;
        """
    )
    conn.commit()
    return conn


def _conteudo(conn, tabelas=TABELAS_V4):
    return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2")] for t in tabelas}


def _sql_plataformas(conn):
    return conn.execute("SELECT sql FROM sqlite_master WHERE name = 'plataformas'").fetchone()[0]


def test_base_v4_migra_para_v5_sem_perder_dados(tmp_path):
    conn = _base_v4(tmp_path / "v4.db")
    antes = _conteudo(conn)

    db.init_db(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert _conteudo(conn) == antes  # mesmos ids, saldos, datas, plano, configuração e depósitos
    assert "REFERENCES categorias(codigo)" in _sql_plataformas(conn)
    assert "CHECK (categoria IN" not in _sql_plataformas(conn)
    assert [tuple(r) for r in conn.execute("SELECT codigo, nome, cor FROM categorias ORDER BY ordem")] == list(db.CATEGORIAS_BASE)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1  # volta a ficar ligada


def test_depois_da_migracao_as_ligacoes_continuam_a_funcionar(tmp_path):
    conn = _base_v4(tmp_path / "v4.db")
    db.init_db(conn)
    with pytest.raises(sqlite3.IntegrityError):  # categoria que não existe na tabela
        conn.execute("INSERT INTO plataformas (nome, categoria, titular) VALUES ('X', 'nao_existe', 'Ana')")
    with pytest.raises(sqlite3.IntegrityError):  # categoria em uso não se apaga
        conn.execute("DELETE FROM categorias WHERE codigo = 'p2p'")
    with pytest.raises(sqlite3.IntegrityError):  # plataforma com registos continua protegida
        conn.execute("DELETE FROM plataformas WHERE id = 3")
    conn.rollback()
    conn.execute("INSERT INTO categorias VALUES ('nova', 'Nova', '#123456', 11)")
    conn.execute("INSERT INTO plataformas (nome, categoria, titular) VALUES ('Y', 'nova', 'Rui')")
    conn.commit()


def test_migracao_v5_e_idempotente_e_nao_repoe_categorias_apagadas(tmp_path):
    conn = _base_v4(tmp_path / "v4.db")
    db.init_db(conn)
    conn.execute("DELETE FROM categorias WHERE codigo = 'cripto'")  # sem plataformas: pode apagar-se
    conn.execute("UPDATE categorias SET nome = 'Liberdade' WHERE codigo = 'emergencia'")
    conn.commit()
    depois = _conteudo(conn, TABELAS_V4 + ("categorias",))

    db.init_db(conn)
    db.init_db(conn)

    assert _conteudo(conn, TABELAS_V4 + ("categorias",)) == depois


def test_migracao_com_categoria_desconhecida_aborta_sem_estragar_nada(tmp_path):
    # Uma base v1 não tinha o CHECK: uma categoria fora da lista faria a migração deixar uma ligação inválida.
    caminho = tmp_path / "v1.db"
    conn = db.connect(caminho)
    conn.executescript(ESQUEMA_V1.replace("'p2p'", "'outra'"))
    with pytest.raises(RuntimeError, match="versão 5"):
        db.init_db(conn)
    conn.close()

    conn = db.connect(caminho)
    assert conn.execute("SELECT categoria FROM plataformas").fetchall()[0][0] == "outra"
    assert conn.execute("SELECT COUNT(*) FROM registos_mensais").fetchone()[0] == 1
    assert "REFERENCES categorias" not in _sql_plataformas(conn)  # a troca foi desfeita
    assert conn.execute("PRAGMA user_version").fetchone()[0] < 5


def test_restaura_copia_v4_sem_categorias_csv(tmp_path):
    conn = _base_v4(tmp_path / "v4.db")
    db.init_db(conn)
    copia = backup.exportar_csv(conn, tmp_path / "backup", agora=datetime(2026, 10, 21, 12, 0, 0))
    (copia / "categorias.csv").unlink()  # como uma cópia feita antes da v5

    destino = tmp_path / "restaurada.db"
    contagens = restauro.restaurar(copia, destino)

    assert contagens["categorias"] == 0 and contagens["plataformas"] == 2
    nova = db.connect(destino)
    assert nova.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == len(db.CATEGORIAS_BASE)


def test_restaura_categorias_criadas_e_renomeadas(tmp_path):
    conn = _base_v4(tmp_path / "v4.db")
    db.init_db(conn)
    conn.execute("INSERT INTO categorias VALUES ('rendimento_extra', 'Rendimento extra', '#123456', 11)")
    conn.execute("UPDATE plataformas SET categoria = 'rendimento_extra' WHERE id = 7")
    conn.execute("UPDATE categorias SET nome = 'P2P (empréstimos)' WHERE codigo = 'p2p'")
    conn.execute("DELETE FROM categorias WHERE codigo = 'cripto'")
    conn.commit()
    copia = backup.exportar_csv(conn, tmp_path / "backup", agora=datetime(2026, 10, 21, 12, 0, 0))

    destino = tmp_path / "restaurada.db"
    restauro.restaurar(copia, destino)

    nova = db.connect(destino)
    tabelas = TABELAS_V4 + ("categorias",)
    assert _conteudo(nova, tabelas) == _conteudo(conn, tabelas)


# --- Versão 5 -> 6: índices de referência --------------------------------------------------------------------

ESQUEMA_V5 = (Path(__file__).parent / "esquema_v5.sql").read_text(encoding="utf-8")
TABELAS_V5 = TABELAS_V4 + ("categorias",)


def _base_v5(caminho):
    conn = db.connect(caminho)
    conn.executescript(ESQUEMA_V5)
    conn.executescript(
        """
        INSERT INTO categorias VALUES ('extra', 'Extra', '#1f9e89', 11);
        INSERT INTO plataformas (id, nome, categoria, titular, plano_mensal_cent, ordem) VALUES
            (3, 'P2P Exemplo', 'p2p', 'Ana', 0, 10), (7, 'Corretora Exemplo', 'investimento', 'Rui', 5000, 20);
        INSERT INTO registos_mensais VALUES (3, '2026-09', 100000, 0, '2026-09-13'), (7, '2026-10', 300000, 5000, '2026-10-01');
        INSERT INTO planos (id, plataforma_id, tipo, data_inicio) VALUES (5, 3, 'desafio_52', '2026-01-01');
        INSERT INTO configuracao VALUES ('despesa_mensal_cent', 150000);
        """
    )
    conn.commit()
    return conn


def test_base_v5_migra_para_v6_sem_perder_dados(tmp_path):
    conn = _base_v5(tmp_path / "v5.db")
    antes = _conteudo(conn, TABELAS_V5)

    db.init_db(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION == 6
    assert _conteudo(conn, TABELAS_V5) == antes  # inclui a categoria criada na app e os nomes editados
    assert conn.execute("SELECT COUNT(*) FROM indices").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM valores_indice").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_tabelas_v6_validam_os_dados(tmp_path):
    conn = _base_v5(tmp_path / "v5.db")
    db.init_db(conn)
    conn.execute("INSERT INTO indices (id, nome, perimetro) VALUES (1, 'Ações mundo', 'investimento'), (2, 'Inflação', NULL)")
    conn.execute("INSERT INTO valores_indice VALUES (1, '2026-10', 1301450)")
    for sql in (
        "INSERT INTO indices (nome, perimetro) VALUES ('ações MUNDO', NULL)",  # nome repetido
        "INSERT INTO indices (nome, perimetro) VALUES ('X', 'nao_existe')",  # categoria inexistente
        "INSERT INTO valores_indice VALUES (1, '2026-13', 10)",  # mês impossível
        "INSERT INTO valores_indice VALUES (2, '2026-10', 0)",  # valor tem de ser positivo
        "INSERT INTO valores_indice VALUES (9, '2026-10', 10)",  # índice inexistente
        "DELETE FROM categorias WHERE codigo = 'investimento'",  # categoria usada como perímetro
    ):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)
    conn.execute("DELETE FROM indices WHERE id = 1")  # apagar o índice leva os valores
    assert conn.execute("SELECT COUNT(*) FROM valores_indice").fetchone()[0] == 0


def test_migracao_v6_e_idempotente(tmp_path):
    conn = _base_v5(tmp_path / "v5.db")
    db.init_db(conn)
    conn.execute("INSERT INTO indices (id, nome) VALUES (1, 'Inflação')")
    conn.execute("INSERT INTO valores_indice VALUES (1, '2026-10', 1184200)")
    conn.commit()
    depois = _conteudo(conn, TABELAS_V5 + ("indices", "valores_indice"))

    db.init_db(conn)

    assert _conteudo(conn, TABELAS_V5 + ("indices", "valores_indice")) == depois


def test_copia_v6_restaura_indices(tmp_path):
    conn = _base_v5(tmp_path / "v5.db")
    db.init_db(conn)
    conn.execute("INSERT INTO indices (id, nome, perimetro, ativo, ordem) VALUES (1, 'Ações mundo', 'investimento', 0, 3)")
    conn.execute("INSERT INTO valores_indice VALUES (1, '2026-10', 1301450)")
    conn.commit()
    copia = backup.exportar_csv(conn, tmp_path / "backup", agora=datetime(2026, 10, 22, 12, 0, 0))

    destino = tmp_path / "restaurada.db"
    contagens = restauro.restaurar(copia, destino)

    assert contagens["indices"] == 1 and contagens["valores_indice"] == 1
    nova = db.connect(destino)
    assert tuple(nova.execute("SELECT * FROM indices").fetchone()) == (1, "Ações mundo", "investimento", 0, 3)
    assert tuple(nova.execute("SELECT * FROM valores_indice").fetchone()) == (1, "2026-10", 1301450)


def test_restaura_copia_v5_sem_csv_dos_indices(tmp_path):
    conn = _base_v5(tmp_path / "v5.db")
    db.init_db(conn)
    copia = backup.exportar_csv(conn, tmp_path / "backup", agora=datetime(2026, 10, 22, 12, 0, 0))
    (copia / "indices.csv").unlink()  # como uma cópia feita antes da v6
    (copia / "valores_indice.csv").unlink()

    contagens = restauro.restaurar(copia, tmp_path / "restaurada.db")

    assert contagens["indices"] == 0 and contagens["valores_indice"] == 0 and contagens["plataformas"] == 2
