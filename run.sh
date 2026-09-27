#!/bin/bash

# ==============================================================================
#  SCRIPT DE INICIALIZAÇÃO: AGENTE BANCO ÁGIL (GOOGLE ADK)
# ==============================================================================

echo "----------------------------------------------------------------------"
echo "🏦 Iniciando o Agente de Atendimento Banco Ágil..."
echo "----------------------------------------------------------------------"

# Sob o capô, o Google ADK é um servidor FastAPI rodando via Uvicorn.
# O comando abaixo inicializa o servidor de API do ADK via Uvicorn expondo na porta 8000.
# O 'exec' garante que o processo python herde o PID 1 do container, 
# permitindo que sinais de terminação (SIGTERM/SIGINT) do OpenShift sejam tratados corretamente.
#exec adk api_server --host 0.0.0.0 --port 8080
exec uvicorn main:app --host 0.0.0.0 --port 8085
 
