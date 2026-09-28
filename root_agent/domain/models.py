from pydantic import BaseModel
from typing import Optional

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
