"""Autenticação: login com bloqueio por tentativas e troca de senha."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from sst.config import get_settings
from sst import demo
from sst.domain.enums import AcaoAuditoria, Perfil
from sst.domain.exceptions import AutenticacaoError, ValidacaoError
from sst.domain.permissoes import UsuarioContexto
from sst.domain.validadores import problemas_senha
from sst.infra.db.base import utcnow
from sst.infra.db.engine import session_scope
from sst.infra.db.models import Tenant, Usuario, UsuarioUnidade
from sst.infra.seguranca import HASH_FALSO, gerar_hash_senha, verificar_senha
from sst.logging_config import get_logger
from sst.services import auditoria_service as auditoria
from sst.services._util import como_utc

log = get_logger(__name__)

MSG_FALHA = "Usuário ou senha inválidos (após várias tentativas a conta é bloqueada temporariamente)."


def _contexto(s, u: Usuario) -> UsuarioContexto:
    unidades = tuple(
        s.scalars(select(UsuarioUnidade.unidade_id).where(UsuarioUnidade.usuario_id == u.id))
    )
    return UsuarioContexto(
        usuario_id=u.id,
        tenant_id=u.tenant_id,
        nome=u.nome,
        email=u.email,
        perfil=Perfil(u.perfil),
        unidades_ids=unidades,
    )


class AuthService:
    @staticmethod
    def autenticar(email: str, senha: str) -> tuple[UsuarioContexto, bool]:
        """Retorna (contexto, deve_trocar_senha). Lança AutenticacaoError com mensagem genérica."""
        settings = get_settings()
        email = (email or "").strip().lower()
        falhou = False
        resultado: tuple[UsuarioContexto, bool] | None = None

        # O commit acontece mesmo quando o login falha (contador de tentativas),
        # por isso a exceção só é lançada depois de sair do session_scope.
        with session_scope() as s:
            u = s.scalars(select(Usuario).where(Usuario.email == email)).first()
            if u is None:
                verificar_senha(senha, HASH_FALSO)  # tempo constante
                falhou = True
                auditoria.registrar(s, None, AcaoAuditoria.LOGIN_FALHA, "Usuario", None,
                                    usuario_email=email[:200])
            else:
                agora = utcnow()
                tenant = s.get(Tenant, u.tenant_id)
                bloqueado = como_utc(u.bloqueado_ate) is not None and como_utc(u.bloqueado_ate) > agora
                senha_ok = verificar_senha(senha, u.senha_hash)
                if bloqueado or not u.ativo or not (tenant and tenant.ativo) or not senha_ok:
                    falhou = True
                    if not bloqueado and not senha_ok:
                        u.tentativas_falhas += 1
                        if u.tentativas_falhas >= settings.login_max_tentativas:
                            u.bloqueado_ate = agora + timedelta(minutes=settings.login_bloqueio_min)
                            u.tentativas_falhas = 0
                            log.warning("Usuário id=%s bloqueado por excesso de tentativas", u.id)
                    auditoria.registrar(s, None, AcaoAuditoria.LOGIN_FALHA, "Usuario", u.id,
                                        tenant_id=u.tenant_id, usuario_email=u.email, usuario_id=u.id)
                else:
                    u.tentativas_falhas = 0
                    u.bloqueado_ate = None
                    u.ultimo_login_em = agora
                    ctx = _contexto(s, u)
                    auditoria.registrar(s, ctx, AcaoAuditoria.LOGIN, "Usuario", u.id)
                    resultado = (ctx, bool(u.deve_trocar_senha))
        if falhou or resultado is None:
            log.info("Falha de login")
            raise AutenticacaoError(MSG_FALHA)
        log.info("Login usuário id=%s tenant=%s", resultado[0].usuario_id, resultado[0].tenant_id)
        return resultado

    @staticmethod
    def recarregar_contexto(ctx: UsuarioContexto) -> UsuarioContexto:
        """Revalida o usuário a cada carregamento de página (perfil/escopo/inativação)."""
        with session_scope() as s:
            u = s.get(Usuario, ctx.usuario_id)
            tenant = s.get(Tenant, ctx.tenant_id)
            if u is None or not u.ativo or u.tenant_id != ctx.tenant_id or not (tenant and tenant.ativo):
                raise AutenticacaoError("Sessão encerrada: usuário inativo ou removido.")
            return _contexto(s, u)

    @staticmethod
    def registrar_logout(ctx: UsuarioContexto) -> None:
        with session_scope() as s:
            auditoria.registrar(s, ctx, AcaoAuditoria.LOGOUT, "Usuario", ctx.usuario_id)

    @staticmethod
    def trocar_senha(ctx: UsuarioContexto, senha_atual: str, nova: str, confirmacao: str) -> None:
        demo.proteger_conta_demo(ctx.email)
        erros = problemas_senha(nova or "")
        if nova != confirmacao:
            erros.append("a confirmação não confere com a nova senha")
        if senha_atual and nova == senha_atual:
            erros.append("a nova senha deve ser diferente da atual")
        if erros:
            raise ValidacaoError(erros)
        with session_scope() as s:
            u = s.get(Usuario, ctx.usuario_id)
            if u is None or u.tenant_id != ctx.tenant_id:
                raise AutenticacaoError("Sessão inválida.")
            if not verificar_senha(senha_atual, u.senha_hash):
                raise ValidacaoError("Senha atual incorreta.")
            u.senha_hash = gerar_hash_senha(nova)
            u.deve_trocar_senha = False
            auditoria.registrar(s, ctx, AcaoAuditoria.TROCAR_SENHA, "Usuario", u.id)
        log.info("Senha alterada usuário id=%s", ctx.usuario_id)
