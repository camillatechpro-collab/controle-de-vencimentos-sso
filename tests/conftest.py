import pytest


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Banco SQLite temporário e isolado por teste."""
    pytest.importorskip("sqlalchemy", reason="SQLAlchemy não instalado")
    from sst import config
    from sst.infra.db import engine as eng

    monkeypatch.setenv("SST_ANEXOS_DIR", str(tmp_path / "anexos"))
    monkeypatch.setenv("SST_LOG_DIR", str(tmp_path / "logs"))
    config.get_settings.cache_clear()
    e = eng.criar_engine(f"sqlite:///{tmp_path / 'teste.db'}")
    eng.definir_engine(e)
    eng.criar_tabelas(e)
    yield e
    eng.definir_engine(None)
    e.dispose()
    config.get_settings.cache_clear()


def _ctx_admin(tenant_id: int, email: str):
    from sqlalchemy import select

    from sst.domain.enums import Perfil
    from sst.domain.permissoes import UsuarioContexto
    from sst.infra.db.engine import session_scope
    from sst.infra.db.models import Usuario

    with session_scope() as s:
        uid = s.scalars(select(Usuario.id).where(Usuario.email == email)).one()
    return UsuarioContexto(uid, tenant_id, "Admin", email, Perfil.ADMIN)


@pytest.fixture
def admin(banco):
    from sst.services.tenant_service import criar_tenant

    tid = criar_tenant("Empresa A", "11222333000181", "Admin A", "admin@a.com.br", "SenhaForte2026")
    return _ctx_admin(tid, "admin@a.com.br")


@pytest.fixture
def admin_b(banco):
    from sst.services.tenant_service import criar_tenant

    tid = criar_tenant("Empresa B", None, "Admin B", "admin@b.com.br", "SenhaForte2026")
    return _ctx_admin(tid, "admin@b.com.br")
