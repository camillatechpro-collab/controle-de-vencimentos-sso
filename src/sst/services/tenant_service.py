"""Criação de empresas (tenants) e configurações da empresa."""

from __future__ import annotations

from typing import Any

from pydantic import Field
from sqlalchemy import func, select

from sst.domain.enums import AcaoAuditoria, Perfil
from sst.domain.exceptions import RegraNegocioError, ValidacaoError
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.domain.validadores import normalizar_cnpj, problemas_senha, validar_cnpj, validar_email
from sst.infra.db.engine import session_scope
from sst.infra.db.models import Tenant, TipoControle, Usuario
from sst.infra.seed_catalogo import CATALOGO_PADRAO
from sst.infra.seguranca import gerar_hash_senha
from sst.logging_config import get_logger
from sst.schemas.base import Entrada, validar
from sst.services import auditoria_service as auditoria

log = get_logger(__name__)


class ConfigEmpresaIn(Entrada):
    nome: str = Field(min_length=2, max_length=150, title="Nome da empresa")
    antecedencia_padrao_dias: int = Field(ge=0, le=365, title="Antecedência padrão (dias)")
    email_alertas: str | None = Field(default=None, title="E-mail para alertas")


def existe_empresa() -> bool:
    """Usado pela tela de login para orientar a primeira instalação."""
    try:
        with session_scope() as s:
            return (s.scalar(select(func.count()).select_from(Tenant)) or 0) > 0
    except Exception:  # banco ainda não criado
        log.exception("Falha ao verificar empresas")
        return False


def criar_tenant(
    nome: str,
    cnpj: str | None,
    admin_nome: str,
    admin_email: str,
    admin_senha: str,
    semear_catalogo: bool = True,
    perfil_admin: Perfil = Perfil.ADMIN,
) -> int:
    """Usado pelos scripts de instalação. Cria empresa + administrador + catálogo."""
    erros: list[str] = []
    if not nome or len(nome.strip()) < 2:
        erros.append("Nome da empresa: obrigatório")
    if cnpj and not validar_cnpj(cnpj):
        erros.append("CNPJ inválido")
    if not validar_email(admin_email):
        erros.append("E-mail do administrador inválido")
    erros += [f"Senha: {p}" for p in problemas_senha(admin_senha)]
    if erros:
        raise ValidacaoError(erros)
    email = admin_email.strip().lower()
    with session_scope() as s:
        if s.scalars(select(Usuario.id).where(Usuario.email == email)).first():
            raise RegraNegocioError("Já existe um usuário com este e-mail.")
        cnpj_n = normalizar_cnpj(cnpj) if cnpj else None
        if cnpj_n and s.scalars(select(Tenant.id).where(Tenant.cnpj == cnpj_n)).first():
            raise RegraNegocioError("Já existe uma empresa com este CNPJ.")
        t = Tenant(nome=nome.strip(), cnpj=cnpj_n, ativo=True)
        s.add(t)
        s.flush()
        u = Usuario(
            tenant_id=t.id, nome=admin_nome.strip(), email=email, perfil=perfil_admin,
            senha_hash=gerar_hash_senha(admin_senha), deve_trocar_senha=False, ativo=True,
        )
        s.add(u)
        s.flush()
        if semear_catalogo:
            for cat, nome_t, norma, alvo, val, uni, ant, anexo, ch in CATALOGO_PADRAO:
                s.add(TipoControle(
                    tenant_id=t.id, categoria=cat, nome=nome_t, norma_referencia=norma, alvo_tipo=alvo,
                    validade_valor=val, validade_unidade=uni, antecedencia_dias=ant,
                    exige_anexo=anexo, carga_horaria_padrao=ch, ativo=True, criado_por_id=u.id,
                ))
        auditoria.registrar(s, None, AcaoAuditoria.CRIAR, "Tenant", t.id, None, t.to_dict(),
                            tenant_id=t.id, usuario_email="instalacao", usuario_id=None)
        tid = t.id
    log.info("Tenant criado id=%s", tid)
    return tid


class TenantService:
    def __init__(self, ctx: UsuarioContexto):
        self.ctx = ctx

    def obter(self) -> dict[str, Any]:
        self.ctx.exigir(Permissao.LER)
        with session_scope() as s:
            t = s.get(Tenant, self.ctx.tenant_id)
            return t.to_dict()

    def atualizar(self, dados: dict[str, Any]) -> None:
        self.ctx.exigir(Permissao.ADMINISTRAR)
        d = validar(ConfigEmpresaIn, dados)
        if d["email_alertas"] and not validar_email(d["email_alertas"]):
            raise ValidacaoError("E-mail para alertas: e-mail inválido")
        with session_scope() as s:
            t = s.get(Tenant, self.ctx.tenant_id)
            antes = t.to_dict()
            t.nome = d["nome"]
            t.antecedencia_padrao_dias = d["antecedencia_padrao_dias"]
            t.email_alertas = d["email_alertas"]
            s.flush()
            auditoria.registrar(s, self.ctx, AcaoAuditoria.ALTERAR, "Empresa", t.id, antes, t.to_dict())
