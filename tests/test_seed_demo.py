import pytest

from app import calc, db, planos
from scripts import seed_demo


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _registos(conn, nome):
    return conn.execute(
        """SELECT r.mes, r.saldo_cent, r.aporte_cent FROM registos_mensais r
           JOIN plataformas p ON p.id = r.plataforma_id WHERE p.nome = ? ORDER BY r.mes""",
        (nome,),
    ).fetchall()


def _serie(linhas):
    return calc.calcular_serie([calc.Registo(r["mes"], r["saldo_cent"], r["aporte_cent"]) for r in linhas], True)


def test_carrega_plataformas_plano_e_registos(conn):
    seed_demo.carregar(conn)
    n = len(seed_demo.PLATAFORMAS)
    assert conn.execute("SELECT COUNT(*) FROM plataformas").fetchone()[0] == n
    assert conn.execute("SELECT COUNT(*) FROM planos").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM registos_mensais").fetchone()[0] == n * len(seed_demo.LEITURAS)


def test_ganhos_positivos_e_sem_avisos(conn):
    seed_demo.carregar(conn)
    for nome, _cat, _titular, _plano, ganho, _aloc in seed_demo.PLATAFORMAS:
        if not ganho:
            continue
        for resultado in _serie(_registos(conn, nome))[1:]:  # o primeiro é o saldo inicial
            assert resultado.ganho_cent > 0, nome
            assert not resultado.avisos, nome


def test_rendimento_da_p2p_ficticia_nao_dispara_avisos(conn):
    seed_demo.carregar(conn)
    linhas = _registos(conn, seed_demo.NOME_P2P)
    serie = _serie(linhas)
    for i in range(1, len(linhas)):
        dias = (seed_demo.LEITURAS[i] - seed_demo.LEITURAS[i - 1]).days
        assert planos.aviso_rendimento(serie[i].ganho_cent, linhas[i - 1]["saldo_cent"], dias) is None


def test_recusa_sem_pwm_db_e_sem_pwm_backup(monkeypatch, capsys):
    monkeypatch.delenv("PWM_DB", raising=False)
    monkeypatch.delenv("PWM_BACKUP", raising=False)
    assert seed_demo.main() == 1
    assert "PWM_DB e PWM_BACKUP" in capsys.readouterr().out


def test_recusa_sem_pwm_backup(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "demo.db"))
    monkeypatch.delenv("PWM_BACKUP", raising=False)
    assert seed_demo.main() == 1
    assert "PWM_BACKUP" in capsys.readouterr().out
    assert not (tmp_path / "demo.db").exists()  # recusou antes de abrir a base


def test_carrega_uma_vez_e_recusa_base_com_dados(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_DB", str(tmp_path / "demo.db"))
    monkeypatch.setenv("PWM_BACKUP", str(tmp_path / "demo-backup"))
    assert seed_demo.main() == 0
    assert seed_demo.main() == 1


def test_demo_confirma_os_depositos_do_desafio(conn):
    seed_demo.carregar(conn)
    soma = conn.execute("SELECT SUM(valor_cent) FROM depositos_desafio").fetchone()[0]
    aportes = sum(r["aporte_cent"] for r in _registos(conn, seed_demo.NOME_P2P))
    assert soma == aportes > 0
