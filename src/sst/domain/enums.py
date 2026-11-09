"""Enumerações do domínio. Valores = nomes (gravados como texto no banco)."""

from __future__ import annotations

from enum import StrEnum


class Rotulado(StrEnum):
    """StrEnum com rótulo amigável em pt-BR."""

    @property
    def rotulo(self) -> str:
        return _ROTULOS.get(self.value, self.value.replace("_", " ").title())

    @classmethod
    def opcoes(cls) -> dict[str, str]:
        return {m.value: m.rotulo for m in cls}


class Perfil(Rotulado):
    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"
    GESTOR_SST = "GESTOR_SST"
    TECNICO_SST = "TECNICO_SST"
    CONSULTA = "CONSULTA"


class Categoria(Rotulado):
    TREINAMENTO = "TREINAMENTO"
    EXAME = "EXAME"
    EQUIPAMENTO = "EQUIPAMENTO"
    DOCUMENTO = "DOCUMENTO"
    CONTRATO = "CONTRATO"
    CERTIFICADO = "CERTIFICADO"
    OBRIGACAO = "OBRIGACAO"


class AlvoTipo(Rotulado):
    COLABORADOR = "COLABORADOR"
    EQUIPAMENTO = "EQUIPAMENTO"
    UNIDADE = "UNIDADE"
    FORNECEDOR = "FORNECEDOR"
    EMPRESA = "EMPRESA"


class ValidadeUnidade(Rotulado):
    DIAS = "DIAS"
    MESES = "MESES"
    ANOS = "ANOS"
    MANUAL = "MANUAL"            # data de vencimento sempre informada (ex.: validade do CA, AVCB)
    SEM_VALIDADE = "SEM_VALIDADE"


class SituacaoVencimento(Rotulado):
    """Estado de ciclo de vida (persistido)."""

    ATIVO = "ATIVO"
    RENOVADO = "RENOVADO"
    CANCELADO = "CANCELADO"


class StatusVencimento(Rotulado):
    """Status calculado (NUNCA persistido)."""

    VENCIDO = "VENCIDO"
    A_VENCER = "A_VENCER"
    VIGENTE = "VIGENTE"
    SEM_VALIDADE = "SEM_VALIDADE"
    RENOVADO = "RENOVADO"
    CANCELADO = "CANCELADO"


class SituacaoColaborador(Rotulado):
    ATIVO = "ATIVO"
    AFASTADO = "AFASTADO"
    DESLIGADO = "DESLIGADO"


class SituacaoEquipamento(Rotulado):
    ATIVO = "ATIVO"
    MANUTENCAO = "MANUTENCAO"
    BAIXADO = "BAIXADO"


class TipoFornecedor(Rotulado):
    CLINICA = "CLINICA"
    TREINAMENTO = "TREINAMENTO"
    PRESTADOR = "PRESTADOR"
    LABORATORIO = "LABORATORIO"
    OUTRO = "OUTRO"


class TipoASO(Rotulado):
    ADMISSIONAL = "ADMISSIONAL"
    PERIODICO = "PERIODICO"
    RETORNO = "RETORNO"
    MUDANCA_RISCO = "MUDANCA_RISCO"
    DEMISSIONAL = "DEMISSIONAL"


class ResultadoASO(Rotulado):
    APTO = "APTO"
    APTO_RESTRICAO = "APTO_RESTRICAO"
    INAPTO = "INAPTO"


class Modalidade(Rotulado):
    PRESENCIAL = "PRESENCIAL"
    EAD = "EAD"
    SEMIPRESENCIAL = "SEMIPRESENCIAL"


class TipoServicoEquipamento(Rotulado):
    RECARGA = "RECARGA"
    INSPECAO = "INSPECAO"
    CALIBRACAO = "CALIBRACAO"
    TESTE_HIDROSTATICO = "TESTE_HIDROSTATICO"
    VALIDADE_CA = "VALIDADE_CA"
    MANUTENCAO = "MANUTENCAO"
    OUTRO = "OUTRO"


class AcaoAuditoria(Rotulado):
    CRIAR = "CRIAR"
    ALTERAR = "ALTERAR"
    EXCLUIR = "EXCLUIR"
    RESTAURAR = "RESTAURAR"
    RENOVAR = "RENOVAR"
    CANCELAR = "CANCELAR"
    LOGIN = "LOGIN"
    LOGIN_FALHA = "LOGIN_FALHA"
    LOGOUT = "LOGOUT"
    TROCAR_SENHA = "TROCAR_SENHA"
    RESETAR_SENHA = "RESETAR_SENHA"
    EXPORTAR = "EXPORTAR"
    VISUALIZAR_SENSIVEL = "VISUALIZAR_SENSIVEL"
    ANEXAR = "ANEXAR"
    BAIXAR_ANEXO = "BAIXAR_ANEXO"


_ROTULOS: dict[str, str] = {
    # perfis
    "SUPERADMIN": "Superadministrador",
    "ADMIN": "Administrador",
    "GESTOR_SST": "Gestor SST",
    "TECNICO_SST": "Técnico SST",
    "CONSULTA": "Consulta",
    # categorias
    "TREINAMENTO": "Treinamento",
    "EXAME": "Exame",
    "EQUIPAMENTO": "Equipamento",
    "DOCUMENTO": "Documento",
    "CONTRATO": "Contrato",
    "CERTIFICADO": "Certificado",
    "OBRIGACAO": "Obrigação",
    # alvos
    "COLABORADOR": "Colaborador",
    "UNIDADE": "Unidade",
    "FORNECEDOR": "Fornecedor",
    "EMPRESA": "Empresa",
    # validade
    "DIAS": "Dias",
    "MESES": "Meses",
    "ANOS": "Anos",
    "MANUAL": "Informada manualmente",
    "SEM_VALIDADE": "Sem validade",
    # status / situações
    "ATIVO": "Ativo",
    "RENOVADO": "Renovado",
    "CANCELADO": "Cancelado",
    "VENCIDO": "Vencido",
    "A_VENCER": "A vencer",
    "VIGENTE": "Vigente",
    "AFASTADO": "Afastado",
    "DESLIGADO": "Desligado",
    "MANUTENCAO": "Manutenção",
    "BAIXADO": "Baixado",
    # fornecedores
    "CLINICA": "Clínica",
    "PRESTADOR": "Prestador de serviço",
    "LABORATORIO": "Laboratório",
    "OUTRO": "Outro",
    # ASO
    "ADMISSIONAL": "Admissional",
    "PERIODICO": "Periódico",
    "RETORNO": "Retorno ao trabalho",
    "MUDANCA_RISCO": "Mudança de risco",
    "DEMISSIONAL": "Demissional",
    "APTO": "Apto",
    "APTO_RESTRICAO": "Apto com restrição",
    "INAPTO": "Inapto",
    # modalidade
    "PRESENCIAL": "Presencial",
    "EAD": "EAD",
    "SEMIPRESENCIAL": "Semipresencial",
    # serviço equipamento
    "RECARGA": "Recarga",
    "INSPECAO": "Inspeção",
    "CALIBRACAO": "Calibração",
    "TESTE_HIDROSTATICO": "Teste hidrostático",
    "VALIDADE_CA": "Validade do CA",
    # auditoria
    "CRIAR": "Criação",
    "ALTERAR": "Alteração",
    "EXCLUIR": "Exclusão",
    "RESTAURAR": "Restauração",
    "RENOVAR": "Renovação",
    "CANCELAR": "Cancelamento",
    "LOGIN": "Login",
    "LOGIN_FALHA": "Falha de login",
    "LOGOUT": "Logout",
    "TROCAR_SENHA": "Troca de senha",
    "RESETAR_SENHA": "Reset de senha",
    "EXPORTAR": "Exportação",
    "VISUALIZAR_SENSIVEL": "Visualização de dado sensível",
    "ANEXAR": "Anexo enviado",
    "BAIXAR_ANEXO": "Anexo baixado",
}

# Categoria → tabela de extensão usada
CATEGORIAS_COM_EXTENSAO = {
    Categoria.TREINAMENTO,
    Categoria.EXAME,
    Categoria.CONTRATO,
    Categoria.EQUIPAMENTO,
}
