from pydantic import BaseModel, Field
from typing import List, Optional

class BankingSubAgentInput(BaseModel):
    cpf: str = Field(description="CPF do cliente autenticado.")
    nome_cliente: str = Field(description="Nome do cliente autenticado.")
    mensagem_usuario: str = Field(description="Intenção do usuário e contexto relevante da conversa.")

class ClienteDTO(BaseModel):
    cpf: str
    nome: str
    data_nascimento: str
    score_credito: int
    limite_credito: float
    conta: str

class SolicitacaoLimiteDTO(BaseModel):
    aprovado: bool
    motivo: str
    limite_anterior: float
    limite_novo: Optional[float]
    limite_maximo_permitido: Optional[float] = None

class RegraScoreLimiteDTO(BaseModel):
    score_min: int
    score_max: int
    limite_maximo: float

class CotacaoDTO(BaseModel):
    moeda_origem: str
    moeda_destino: str
    taxa: float
    timestamp: str
    erro: Optional[str] = None

class EntrevistaDTO(BaseModel):
    renda_mensal: float
    tipo_emprego: str
    despesas_mensais: float
    num_dependentes: int
    tem_dividas: bool
    novo_score: int
