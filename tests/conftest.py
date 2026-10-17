import pytest


@pytest.fixture(autouse=True)
def _backup_isolado(monkeypatch, tmp_path_factory):
    """Nenhum teste escreve na pasta backup\\ real: cada teste usa uma pasta temporária."""
    monkeypatch.setenv("PWM_BACKUP", str(tmp_path_factory.mktemp("backup")))
