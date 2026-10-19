import csv
from datetime import datetime, timedelta

import pytest

from app import db
from app.backup import TABELAS, exportar_csv


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    c.execute("INSERT INTO plataformas (nome, categoria, titular) VALUES ('Degiro', 'investimento', 'Miguel')")
    c.execute(
        "INSERT INTO registos_mensais (plataforma_id, mes, saldo_cent, aporte_cent, data_leitura) "
        "VALUES (1, '2026-10', 123456, 5000, '2026-10-13')"
    )
    c.commit()
    yield c
    c.close()


AGORA = datetime(2026, 11, 1, 9, 30, 0)


def _alterar(conn, valor):
    """Muda o conteúdo para a cópia seguinte não ser igual à anterior."""
    conn.execute("UPDATE registos_mensais SET saldo_cent = ?", (valor,))
    conn.commit()


def test_cria_um_csv_por_tabela(conn, tmp_path):
    destino = exportar_csv(conn, tmp_path, agora=AGORA)
    assert destino.name == "2026-11-01_093000"
    assert {p.name for p in destino.iterdir()} == {f"{t}.csv" for t in TABELAS}


def test_csv_tem_cabecalho_dados_e_separador_ponto_e_virgula(conn, tmp_path):
    destino = exportar_csv(conn, tmp_path, agora=AGORA)
    with open(destino / "registos_mensais.csv", encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.reader(f, delimiter=";"))
    assert linhas[0] == ["plataforma_id", "mes", "saldo_cent", "aporte_cent", "data_leitura"]
    assert linhas[1] == ["1", "2026-10", "123456", "5000", "2026-10-13"]


def test_tabela_vazia_exporta_so_cabecalho(conn, tmp_path):
    destino = exportar_csv(conn, tmp_path, agora=AGORA)
    with open(destino / "planos.csv", encoding="utf-8-sig", newline="") as f:
        assert len(list(csv.reader(f, delimiter=";"))) == 1


def test_nao_sobrescreve_copia_existente(conn, tmp_path):
    exportar_csv(conn, tmp_path, agora=AGORA)
    _alterar(conn, 1)  # conteúdo diferente, mesmo segundo
    with pytest.raises(FileExistsError):
        exportar_csv(conn, tmp_path, agora=AGORA)


def test_nao_deixa_pasta_temporaria(conn, tmp_path):
    exportar_csv(conn, tmp_path, agora=AGORA)
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_mantem_apenas_as_mais_recentes(conn, tmp_path):
    for i in range(5):
        _alterar(conn, i)
        exportar_csv(conn, tmp_path, agora=AGORA + timedelta(minutes=i), manter=3)
    nomes = sorted(p.name for p in tmp_path.iterdir())
    assert nomes == ["2026-11-01_093200", "2026-11-01_093300", "2026-11-01_093400"]


def test_limpeza_nao_toca_noutras_pastas_nem_ficheiros(conn, tmp_path):
    (tmp_path / "notas").mkdir()
    (tmp_path / "leia-me.txt").write_text("não apagar")
    for i in range(3):
        _alterar(conn, i)
        exportar_csv(conn, tmp_path, agora=AGORA + timedelta(minutes=i), manter=1)
    assert (tmp_path / "notas").is_dir()
    assert (tmp_path / "leia-me.txt").exists()


def test_manter_invalido(conn, tmp_path):
    with pytest.raises(ValueError):
        exportar_csv(conn, tmp_path, agora=AGORA, manter=0)


def test_conteudo_igual_nao_cria_copia_nova(conn, tmp_path):
    primeira = exportar_csv(conn, tmp_path, agora=AGORA)
    segunda = exportar_csv(conn, tmp_path, agora=AGORA + timedelta(minutes=5))
    assert segunda == primeira
    assert len(list(tmp_path.iterdir())) == 1


def test_conteudo_alterado_cria_copia_nova(conn, tmp_path):
    primeira = exportar_csv(conn, tmp_path, agora=AGORA)
    _alterar(conn, 1)
    segunda = exportar_csv(conn, tmp_path, agora=AGORA + timedelta(minutes=5))
    assert segunda != primeira
    assert len(list(tmp_path.iterdir())) == 2


def test_protege_a_ultima_copia_de_cada_mes(conn, tmp_path):
    datas = [datetime(2026, 9, 15, 12), datetime(2026, 9, 30, 12), datetime(2026, 10, 5, 12),
             datetime(2026, 10, 6, 12), datetime(2026, 10, 7, 12)]
    for i, d in enumerate(datas):
        _alterar(conn, i)
        exportar_csv(conn, tmp_path, agora=d, manter=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "2026-09-30_120000", "2026-10-06_120000", "2026-10-07_120000",
    ]


def test_tabelas_cobrem_todo_o_esquema(conn):
    """Uma tabela nova no esquema tem de entrar em TABELAS, senão fica fora das cópias."""
    nomes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(TABELAS) == nomes


def test_apaga_temporarias_orfas(conn, tmp_path):
    orfa = tmp_path / "2026-10-01_090000.tmp"
    orfa.mkdir()
    (orfa / "plataformas.csv").write_text("meia cópia")
    alheia = tmp_path / "notas.tmp"
    alheia.mkdir()
    exportar_csv(conn, tmp_path, agora=AGORA)
    assert not orfa.exists()
    assert alheia.exists()  # só as que têm o padrão de nome das cópias


def test_renomear_tenta_outra_vez_se_a_pasta_estiver_presa(conn, tmp_path, monkeypatch):
    from pathlib import Path

    from app import backup

    original = Path.rename
    falhas = {"n": 2}

    def presa(self, destino):
        if falhas["n"]:
            falhas["n"] -= 1
            raise PermissionError("pasta em uso")
        return original(self, destino)

    monkeypatch.setattr(Path, "rename", presa)
    monkeypatch.setattr(backup.time, "sleep", lambda _: None)
    destino = exportar_csv(conn, tmp_path, agora=AGORA)
    assert destino.is_dir() and falhas["n"] == 0


def test_renomear_desiste_e_nao_deixa_temporaria(conn, tmp_path, monkeypatch):
    from pathlib import Path

    from app import backup

    def sempre_presa(self, destino):
        raise PermissionError("pasta em uso")

    monkeypatch.setattr(Path, "rename", sempre_presa)
    monkeypatch.setattr(backup.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        exportar_csv(conn, tmp_path, agora=AGORA)
    assert list(tmp_path.iterdir()) == []
