import pytest


@pytest.fixture(autouse=True)
def _backup_isolado(monkeypatch, tmp_path_factory):
    """Nenhum teste escreve na pasta backup\\ real: cada teste usa uma pasta temporária."""
    monkeypatch.setenv("PWM_BACKUP", str(tmp_path_factory.mktemp("backup")))


@pytest.fixture(autouse=True)
def _host_do_testclient(monkeypatch):
    """O TestClient usa o Host 'testserver'; na app real só se aceitam 127.0.0.1 e localhost."""
    from app import main

    monkeypatch.setattr(main, "HOSTS_PERMITIDOS", main.HOSTS_PERMITIDOS | {"testserver"})
