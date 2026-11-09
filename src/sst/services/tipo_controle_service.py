"""Catálogo de tipos de controle."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sst.domain.enums import SituacaoVencimento
from sst.domain.exceptions import RegraNegocioError
from sst.domain.permissoes import Permissao
from sst.infra.db.models import TipoControle, Vencimento
from sst.schemas.cadastros import TipoControleIn
from sst.services.base_crud import CrudService


class TipoControleService(CrudService[TipoControle]):
    model = TipoControle
    schema = TipoControleIn
    entidade = "Tipo de controle"
    campos_unicos = {"nome": "nome"}
    perm_escrita = Permissao.GERENCIAR_CATALOGO

    def _ordem(self):
        return (TipoControle.categoria, TipoControle.nome)

    def _validar_regras(self, s: Session, dados: dict, atual: TipoControle | None) -> None:
        if atual is None:
            return
        mudou = atual.alvo_tipo != dados["alvo_tipo"] or atual.categoria != dados["categoria"]
        if mudou:
            usados = s.scalar(
                select(func.count()).select_from(Vencimento).where(
                    Vencimento.tipo_controle_id == atual.id, Vencimento.excluido_em.is_(None)
                )
            )
            if usados:
                raise RegraNegocioError(
                    "Este tipo já possui vencimentos lançados: não é possível alterar a "
                    "categoria nem a quem se aplica. Crie um novo tipo e inative este."
                )

    def _validar_exclusao(self, s: Session, obj: TipoControle) -> None:
        ativos = s.scalar(
            select(func.count()).select_from(Vencimento).where(
                Vencimento.tipo_controle_id == obj.id,
                Vencimento.excluido_em.is_(None),
                Vencimento.situacao == SituacaoVencimento.ATIVO,
            )
        )
        if ativos:
            raise RegraNegocioError(
                f"Existem {ativos} vencimento(s) ativo(s) deste tipo. Inative o tipo em vez de excluir."
            )

    def opcoes_por_alvo(self) -> dict[int, dict]:
        """{id: {nome, categoria, alvo_tipo, ...}} dos tipos ativos (para formulários)."""
        df = self.listar(incluir_inativos=False)
        return {int(r["id"]): r for r in df.to_dict("records")}
