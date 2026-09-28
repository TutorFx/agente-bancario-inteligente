#!/bin/bash

# ==============================================================================
#  SCRIPT DE INICIALIZAÇÃO: AGENTE BANCO ÁGIL (GOOGLE ADK)
# ==============================================================================

echo "----------------------------------------------------------------------"
echo "Iniciando a API do Banco Ágil..."
echo "----------------------------------------------------------------------"

# Sobe a API (main.py: ADK + middlewares) com Uvicorn na porta 8085.
# Com 'exec', o Python assume o PID 1 do container e recebe SIGTERM/SIGINT diretamente.
exec uvicorn main:app --host 0.0.0.0 --port 8085
 
