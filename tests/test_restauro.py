from datetime import datetime

import pytest

from app import backup, db, restauro


@pytest.fixture
def origem(tmp_path):
    """Base de dados real em ficheiro, com dados que exercitam os casos difíceis."""
    conn = db.connect(tmp_path / "origem.db")
    db.init_db(conn)
    conn.execute(
        """INSERT INTO plataformas (id, nome, categoria, titular, finalidade, plano_mensal_cent, calcula_ganho, entra_alocacao, ordem)
           VALUES (1, 'XTB; com ponto e vírgula', 'investimento', 'Miguel', 'Fundo de teste', 5000, 1, 1, 7)"""
    )  # ';' no nome e finalidade preenchida
    conn.execute(
        """INSERT INTO plataformas (id, nome, categoria, titular, plano_mensal_cent, calcula_ganho, entra_alocacao, ordem)
           VALUES (2, 'Conta "Principal"', 'conta_corrente', 'Conjunto', 0, 0, 0, 1)"""
    )  # aspas no nome e finalidade NULL
    conn.executemany(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "2026-09", 100000, 5000, None),  # registo sem data (anterior à versão 2)
            (1, "2026-10", 104000, -2000, "2026-10-13"),
            (2, "2026-10", 28824, 0, None),
        ],
    )
    conn.execute("INSERT INTO planos (plataforma_id, tipo, data_inicio) VALUES (1, 'dca', '2024-01-01')")
    conn.execute("INSERT INTO configuracao (chave, valor) VALUES ('despesa_mensal_cent', 150000)")
    conn.commit()
    yield conn
    conn.close()


def _tudo(conn):
    return {
        t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2")] for t in backup.TABELAS
    }


def _exportar(origem, tmp_path, agora=datetime(2026, 10, 13, 20, 0, 0)):
    return backup.exportar_csv(origem, tmp_path / "backup", agora=agora)


def test_ida_e_volta_reproduz_exatamente_os_dados(origem, tmp_path):
    copia = _exportar(origem, tmp_path)
    destino = tmp_path / "restaurada.db"

    contagens = restauro.restaurar(copia, destino)

    assert contagens == {"categorias": len(db.CATEGORIAS_BASE), "plataformas": 2, "registos_mensais": 3, "planos": 1, "configuracao": 1, "depositos_desafio": 0}
    nova = db.connect(destino)
    try:
        assert _tudo(nova) == _tudo(origem)  # inclui NULL, ';', aspas e aporte negativo
    finally:
        nova.close()


def test_nunca_sobrescreve_um_ficheiro_existente(origem, tmp_path):
    copia = _exportar(origem, tmp_path)
    destino = tmp_path / "ja_existe.db"
    destino.write_bytes(b"nao mexer")

    with pytest.raises(FileExistsError):
        restauro.restaurar(copia, destino)
    assert destino.read_bytes() == b"nao mexer"


def test_nao_toca_na_base_de_origem(origem, tmp_path):
    antes = _tudo(origem)
    copia = _exportar(origem, tmp_path)
    restauro.restaurar(copia, tmp_path / "restaurada.db")
    assert _tudo(origem) == antes


def test_cabecalho_diferente_falha_sem_deixar_ficheiro(origem, tmp_path):
    copia = _exportar(origem, tmp_path)
    csv_reg = copia / "registos_mensais.csv"
    texto = csv_reg.read_text(encoding="utf-8-sig").replace("saldo_cent", "saldo")
    csv_reg.write_text(texto, encoding="utf-8-sig")
    destino = tmp_path / "restaurada.db"

    with pytest.raises(ValueError, match="colunas"):
        restauro.restaurar(copia, destino)
    assert not destino.exists()


def test_valor_nao_inteiro_falha_sem_deixar_ficheiro(origem, tmp_path):
    copia = _exportar(origem, tmp_path)
    csv_reg = copia / "registos_mensais.csv"
    texto = csv_reg.read_text(encoding="utf-8-sig").replace("104000", "abc")
    csv_reg.write_text(texto, encoding="utf-8-sig")
    destino = tmp_path / "restaurada.db"

    with pytest.raises(ValueError, match="não é inteiro"):
        restauro.restaurar(copia, destino)
    assert not destino.exists()


def test_dados_que_violam_o_esquema_falham_sem_deixar_ficheiro(origem, tmp_path):
    copia = _exportar(origem, tmp_path)
    csv_reg = copia / "registos_mensais.csv"
    texto = csv_reg.read_text(encoding="utf-8-sig").replace("2026-09", "2026-13")  # mês impossível
    csv_reg.write_text(texto, encoding="utf-8-sig")
    destino = tmp_path / "restaurada.db"

    with pytest.raises(Exception):
        restauro.restaurar(copia, destino)
    assert not destino.exists()


def test_ficheiro_em_falta_falha(origem, tmp_path):
    copia = _exportar(origem, tmp_path)
    (copia / "planos.csv").unlink()
    with pytest.raises(FileNotFoundError, match="planos.csv"):
        restauro.restaurar(copia, tmp_path / "restaurada.db")


def test_ultima_copia_escolhe_a_mais_recente_e_ignora_outras_pastas(origem, tmp_path):
    _exportar(origem, tmp_path, datetime(2026, 10, 12, 9, 0, 0))
    recente = _exportar(origem, tmp_path, datetime(2026, 10, 13, 20, 0, 0))
    (tmp_path / "backup" / "lixo").mkdir()
    (tmp_path / "backup" / "2099-01-01_000000.tmp").mkdir()  # cópia incompleta não conta
    assert restauro.ultima_copia(tmp_path / "backup") == recente


def test_ultima_copia_sem_copias_falha(tmp_path):
    with pytest.raises(FileNotFoundError):
        restauro.ultima_copia(tmp_path / "nao_existe")


def test_main_restaura_a_ultima_para_o_destino_indicado(origem, tmp_path, monkeypatch, capsys):
    _exportar(origem, tmp_path)
    monkeypatch.setenv("PWM_BACKUP", str(tmp_path / "backup"))
    destino = tmp_path / "via_cli.db"

    assert restauro.main(["--destino", str(destino)]) == 0
    assert destino.exists()
    assert "a atual não foi tocada" in capsys.readouterr().out


def test_main_devolve_1_e_mensagem_quando_falha(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PWM_BACKUP", str(tmp_path / "vazio"))
    assert restauro.main(["--destino", str(tmp_path / "x.db")]) == 1
    assert "Restauro falhou" in capsys.readouterr().out


def test_copia_anterior_a_tabela_configuracao_restaura_com_a_tabela_vazia(origem, tmp_path):
    """As cópias de antes da versão 3 do esquema não têm configuracao.csv."""
    copia = _exportar(origem, tmp_path)
    (copia / "configuracao.csv").unlink()
    destino = tmp_path / "restaurada.db"

    contagens = restauro.restaurar(copia, destino)

    assert contagens["configuracao"] == 0
    assert contagens["registos_mensais"] == 3


def test_inteiro_fora_do_sqlite_falha_sem_deixar_ficheiro(origem, tmp_path):
    copia = _exportar(origem, tmp_path)
    csv_reg = copia / "registos_mensais.csv"
    texto = csv_reg.read_text(encoding="utf-8-sig").replace("104000", "9" * 25)
    csv_reg.write_text(texto, encoding="utf-8-sig")
    destino = tmp_path / "restaurada.db"

    with pytest.raises(ValueError, match="fora do intervalo"):
        restauro.restaurar(copia, destino)
    assert not destino.exists()
