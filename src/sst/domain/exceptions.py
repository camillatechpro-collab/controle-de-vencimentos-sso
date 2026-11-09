"""Exceções de negócio. A interface mostra `mensagem` ao usuário; tudo o que
não for SSTError é tratado como erro inesperado (logado com rastreio)."""

from __future__ import annotations


class SSTError(Exception):
    """Base de todos os erros esperados da aplicação."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class ValidacaoError(SSTError):
    """Dados de entrada inválidos. `erros` lista mensagens por campo."""

    def __init__(self, erros: list[str] | str):
        self.erros = [erros] if isinstance(erros, str) else list(erros)
        super().__init__("Corrija os campos: " + "; ".join(self.erros))


class RegraNegocioError(SSTError):
    """Operação viola uma regra de negócio."""


class NaoEncontradoError(SSTError):
    def __init__(self, entidade: str, ident: object | None = None):
        detalhe = f" (id {ident})" if ident is not None else ""
        super().__init__(f"{entidade} não encontrado(a){detalhe}.")


class PermissaoNegadaError(SSTError):
    def __init__(self, mensagem: str = "Você não tem permissão para esta operação."):
        super().__init__(mensagem)


class AutenticacaoError(SSTError):
    """Falha de login. Mensagem sempre genérica para não revelar se o usuário existe."""

    def __init__(self, mensagem: str = "Usuário ou senha inválidos."):
        super().__init__(mensagem)
