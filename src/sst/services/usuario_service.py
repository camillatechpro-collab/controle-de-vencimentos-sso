"""Gestão de usuários do tenant."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import func, select

from sst.domain.enums import AcaoAuditoria, Perfil
from sst.domain.exceptions import RegraNegocioError
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.infra.db.engine import session_scope
from sst.infra.db.models import Unidade, Usuario, UsuarioUnidade
from sst.infra.repositories.base import TenantRepository
from sst.infra.seguranca import gerar_hash_senha, gerar_senha_temporaria
from sst.logging_config import get_logger
from sst.schemas.base import validar
from sst.schemas.usuario import UsuarioIn
from sst.services import auditoria_service as auditoria
from sst.services._util import df_de_resultado
from sst.services.base_crud import garantir_do_tenant

log = get_logger(__name__)


class UsuarioService:
    def __init__(self, ctx: UsuarioContexto):
        self.ctx = ctx

    def _repo(self, s) -> TenantRepository[Usuario]:
        return TenantRepository(s, Usuario, self.ctx.tenant_id, "Usuário")

    def _unidades(self, s, usuario_id: int) -> list[int]:
        return list(s.scalars(select(UsuarioUnidade.unidade_id).where(UsuarioUnidade.usuario_id == usuario_id)))

    def _admins_ativos(self, s, excluir_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(Usuario).where(
            Usuario.tenant_id == self.ctx.tenant_id,
            Usuario.ativo.is_(True),
            Usuario.perfil.in_([Perfil.ADMIN, Perfil.SUPERADMIN]),
        )
        if excluir_id:
            stmt = stmt.where(Usuario.id != excluir_id)
        return s.scalar(stmt) or 0

    def listar(self) -> pd.DataFrame:
        self.ctx.exigir(Permissao.GERENCIAR_USUARIOS)
        stmt = (
            select(
                Usuario.id, Usuario.nome, Usuario.email, Usuario.perfil, Usuario.ativo,
                Usuario.deve_trocar_senha, Usuario.bloqueado_ate, Usuario.ultimo_login_em,
            )
            .where(Usuario.tenant_id == self.ctx.tenant_id)
            .order_by(Usuario.nome)
        )
        with session_scope() as s:
            df = df_de_resultado(s.execute(stmt))
            if not df.empty:
                nomes = dict(s.execute(select(Unidade.id, Unidade.nome).where(Unidade.tenant_id == self.ctx.tenant_id)).all())
                vinc = s.execute(
                    select(UsuarioUnidade.usuario_id, UsuarioUnidade.unidade_id)
                    .join(Usuario, Usuario.id == UsuarioUnidade.usuario_id)
                    .where(Usuario.tenant_id == self.ctx.tenant_id)
                ).all()
                mapa: dict[int, list[str]] = {}
                for uid, unid in vinc:
                    mapa.setdefault(uid, []).append(nomes.get(unid, str(unid)))
                df["unidades"] = df["id"].map(lambda i: ", ".join(sorted(mapa.get(i, []))) or "Todas")
        return df

    def obter(self, ident: int) -> dict[str, Any]:
        self.ctx.exigir(Permissao.GERENCIAR_USUARIOS)
        with session_scope() as s:
            u = self._repo(s).obter_ou_erro(ident)
            dados = u.to_dict()
            dados["unidades_ids"] = self._unidades(s, u.id)
            return dados

    def _definir_unidades(self, s, usuario: Usuario, unidades_ids: list[int]) -> None:
        for uid in set(unidades_ids):
            garantir_do_tenant(s, self.ctx, Unidade, uid, "Unidade")
        usuario.unidades.clear()
        s.flush()
        for uid in sorted(set(unidades_ids)):
            usuario.unidades.append(UsuarioUnidade(unidade_id=uid))

    def criar(self, dados: dict[str, Any]) -> tuple[int, str]:
        """Retorna (id, senha_temporária). A senha só é exibida uma vez."""
        self.ctx.exigir(Permissao.GERENCIAR_USUARIOS)
        d = validar(UsuarioIn, dados)
        senha = gerar_senha_temporaria()
        with session_scope() as s:
            if s.scalars(select(Usuario.id).where(Usuario.email == d["email"])).first():
                raise RegraNegocioError("Já existe um usuário com este e-mail.")
            u = Usuario(
                nome=d["nome"], email=d["email"], perfil=d["perfil"], ativo=d["ativo"],
                senha_hash=gerar_hash_senha(senha), deve_trocar_senha=True,
            )
            self._repo(s).adicionar(u, self.ctx.usuario_id)
            self._definir_unidades(s, u, d["unidades_ids"])
            depois = u.to_dict() | {"unidades_ids": d["unidades_ids"]}
            auditoria.registrar(s, self.ctx, AcaoAuditoria.CRIAR, "Usuário", u.id, None, depois)
            novo = u.id
        log.info("Usuário criado id=%s por=%s", novo, self.ctx.usuario_id)
        return novo, senha

    def atualizar(self, ident: int, dados: dict[str, Any]) -> None:
        self.ctx.exigir(Permissao.GERENCIAR_USUARIOS)
        d = validar(UsuarioIn, dados)
        with session_scope() as s:
            u = self._repo(s).obter_ou_erro(ident)
            if Perfil(u.perfil) is Perfil.SUPERADMIN and self.ctx.perfil is not Perfil.SUPERADMIN:
                raise RegraNegocioError("Usuário superadministrador não pode ser alterado aqui.")
            if s.scalars(select(Usuario.id).where(Usuario.email == d["email"], Usuario.id != ident)).first():
                raise RegraNegocioError("Já existe um usuário com este e-mail.")
            if ident == self.ctx.usuario_id and (not d["ativo"] or d["perfil"] != u.perfil):
                raise RegraNegocioError("Você não pode inativar nem mudar o perfil do seu próprio usuário.")
            era_admin = Perfil(u.perfil) in (Perfil.ADMIN, Perfil.SUPERADMIN) and u.ativo
            continua_admin = d["perfil"] in (Perfil.ADMIN, Perfil.SUPERADMIN) and d["ativo"]
            if era_admin and not continua_admin and self._admins_ativos(s, excluir_id=ident) == 0:
                raise RegraNegocioError("A empresa precisa de pelo menos um administrador ativo.")
            antes = u.to_dict() | {"unidades_ids": self._unidades(s, u.id)}
            u.nome, u.email, u.ativo = d["nome"], d["email"], d["ativo"]
            if Perfil(u.perfil) is not Perfil.SUPERADMIN:
                u.perfil = d["perfil"]
            u.atualizado_por_id = self.ctx.usuario_id
            self._definir_unidades(s, u, d["unidades_ids"])
            s.flush()
            depois = u.to_dict() | {"unidades_ids": sorted(set(d["unidades_ids"]))}
            auditoria.registrar(s, self.ctx, AcaoAuditoria.ALTERAR, "Usuário", u.id, antes, depois)

    def resetar_senha(self, ident: int) -> str:
        self.ctx.exigir(Permissao.GERENCIAR_USUARIOS)
        senha = gerar_senha_temporaria()
        with session_scope() as s:
            u = self._repo(s).obter_ou_erro(ident)
            u.senha_hash = gerar_hash_senha(senha)
            u.deve_trocar_senha = True
            u.tentativas_falhas = 0
            u.bloqueado_ate = None
            auditoria.registrar(s, self.ctx, AcaoAuditoria.RESETAR_SENHA, "Usuário", u.id)
        log.info("Senha resetada usuário id=%s por=%s", ident, self.ctx.usuario_id)
        return senha
