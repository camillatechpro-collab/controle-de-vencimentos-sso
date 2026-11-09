"""Importa todos os models para registrá-los no metadata."""

from sst.infra.db.models.auditoria import Auditoria
from sst.infra.db.models.catalogo import RequisitoCargo, TipoControle
from sst.infra.db.models.organizacao import (
    Cargo,
    Colaborador,
    Equipamento,
    Fornecedor,
    Setor,
    Unidade,
)
from sst.infra.db.models.tenant import Tenant
from sst.infra.db.models.usuario import Usuario, UsuarioUnidade
from sst.infra.db.models.vencimento import (
    Anexo,
    TurmaTreinamento,
    VencContrato,
    VencEquipamento,
    VencExame,
    VencTreinamento,
    Vencimento,
)

__all__ = [
    "Anexo",
    "Auditoria",
    "Cargo",
    "Colaborador",
    "Equipamento",
    "Fornecedor",
    "RequisitoCargo",
    "Setor",
    "Tenant",
    "TipoControle",
    "TurmaTreinamento",
    "Unidade",
    "Usuario",
    "UsuarioUnidade",
    "VencContrato",
    "VencEquipamento",
    "VencExame",
    "VencTreinamento",
    "Vencimento",
]
