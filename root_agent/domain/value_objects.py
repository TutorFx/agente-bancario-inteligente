"""Objetos de Valor (Value Objects) do Domínio Bancário."""


class CPF:
    """
    Objeto de Valor que encapsula um Cadastro de Pessoas Físicas (CPF).
    Garante imutabilidade e validações intrínsecas ao dado.
    """

    def __init__(self, valor: str):
        self._valor = valor.strip()

    @property
    def valor(self) -> str:
        return self._valor

    def possui_tamanho_correto(self) -> bool:
        """Verifica se possui exatamente 11 dígitos numéricos."""
        return len(self._valor) == 11 and self._valor.isdigit()

    def possui_digitos_repetidos(self) -> bool:
        """Verifica se todos os 11 dígitos são iguais (ex: 111.111.111-11)."""
        return len(self._valor) == 11 and len(set(self._valor)) == 1

    def formatado(self) -> str:
        """Retorna o CPF formatado no padrão 000.000.000-00."""
        if len(self._valor) == 11 and self._valor.isdigit():
            return f"{self._valor[:3]}.{self._valor[3:6]}.{self._valor[6:9]}-{self._valor[9:]}"
        return self._valor

    def mascarado(self) -> str:
        """Retorna o CPF mascarado para exibição segura em logs e auditoria (LGPD/PII)."""
        if len(self._valor) >= 4:
            return f"***{self._valor[-4:]}"
        return "***"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CPF):
            return self._valor == other._valor
        if isinstance(other, str):
            return self._valor == other
        return False

    def __str__(self) -> str:
        return self.formatado()

    def __repr__(self) -> str:
        return f"CPF('{self.mascarado()}')"
