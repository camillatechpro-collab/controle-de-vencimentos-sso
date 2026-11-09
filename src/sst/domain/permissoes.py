"""RBAC: permissões por perfil e contexto do usuário logado."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sst.domain.enums import Perfil
from sst.domain.exceptions import PermissaoNegadaError


class Permissao(StrEnum):
    LER = "LER"                                  # consultar dados, relatórios, exportar
    EDITAR_CADASTROS = "EDITAR_CADASTROS"        # unidades, colaboradores, equipamentos...
    EDITAR_VENCIMENTOS = "EDITAR_VENCIMENTOS"    # criar / editar / renovar / anexar
    CANCELAR_VENCIMENTOS = "CANCELAR_VENCIMENTOS"  # cancelar e excluir
    GERENCIAR_CATALOGO = "GERENCIAR_CATALOGO"    # tipos de controle e matriz por cargo
    VER_DADOS_SAUDE = "VER_DADOS_SAUDE"          # resultado de ASO
    GERENCIAR_USUARIOS = "GERENCIAR_USUARIOS"
    ADMINISTRAR = "ADMINISTRAR"                  # configurações, lixeira, auditoria


_TODAS = frozenset(Permissao)

PERMISSOES_POR_PERFIL: dict[Perfil, frozenset[Permissao]] = {
    Perfil.SUPERADMIN: _TODAS,
    Perfil.ADMIN: _TODAS,
    Perfil.GESTOR_SST: frozenset(
        {
            Permissao.LER,
            Permissao.EDITAR_CADASTROS,
            Permissao.EDITAR_VENCIMENTOS,
            Permissao.CANCELAR_VENCIMENTOS,
            Permissao.GERENCIAR_CATALOGO,
            Permissao.VER_DADOS_SAUDE,
        }
    ),
    # Decisão conservadora (LGPD): técnico não vê resultado de ASO por padrão.
    Perfil.TECNICO_SST: frozenset(
        {Permissao.LER, Permissao.EDITAR_CADASTROS, Permissao.EDITAR_VENCIMENTOS}
    ),
    Perfil.CONSULTA: frozenset({Permissao.LER}),
}


@dataclass(frozen=True)
class UsuarioContexto:
    """Quem está executando a operação. Criado SOMENTE pelo login."""

    usuario_id: int
    tenant_id: int
    nome: str
    email: str
    perfil: Perfil
    unidades_ids: tuple[int, ...] = field(default_factory=tuple)  # vazio = todas

    def pode(self, permissao: Permissao) -> bool:
        return permissao in PERMISSOES_POR_PERFIL.get(self.perfil, frozenset())

    def exigir(self, permissao: Permissao) -> None:
        if not self.pode(permissao):
            raise PermissaoNegadaError()

    @property
    def restrito_por_unidade(self) -> bool:
        return len(self.unidades_ids) > 0

    def pode_ver_unidade(self, unidade_id: int | None) -> bool:
        if not self.restrito_por_unidade:
            return True
        return unidade_id is None or unidade_id in self.unidades_ids

    def exigir_unidade(self, unidade_id: int | None) -> None:
        if not self.pode_ver_unidade(unidade_id):
            raise PermissaoNegadaError("Você não tem acesso a esta unidade.")
