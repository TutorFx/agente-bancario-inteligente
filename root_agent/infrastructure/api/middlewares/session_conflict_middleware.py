import json
import httpx
from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message

from root_agent.infrastructure.api.queue.session_queue_port import SessionQueuePort
from root_agent.utils import get_logger

logger = get_logger("middleware.session_conflict")

# Utilitário para permitir que o body seja lido mais de uma vez (pelo call_next e pelo httpx)
async def set_body(request: Request, body: bytes):
    async def receive() -> Message:
        return {"type": "http.request", "body": body}
    request._receive = receive

class SessionConflictMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, session_queue: SessionQueuePort):
        super().__init__(app)
        self.session_queue = session_queue

    async def dispatch(self, request: Request, call_next):
        # Filtra apenas POST na rota de sessões para interceptação
        if request.method == "POST" and "sessions" in request.url.path and "run" not in request.url.path:
            import re
            
            # Regex robusto para capturar app_name, user_id e opcionalmente session_id,
            # independente de prefixos na URL (ex: /api/v1/apps/...)
            match = re.search(r"/apps/(?P<app_name>[^/]+)/users/(?P<user_id>[^/]+)/sessions(?:/(?P<session_id>[^/]+))?", request.url.path)
            
            if not match:
                return await call_next(request)
                
            app_name = match.group("app_name")
            user_id = match.group("user_id")
            session_id = match.group("session_id") or user_id
            
            # Copia o body para a memória a fim de poder reusá-lo caso dê erro
            body_bytes = await request.body()
            await set_body(request, body_bytes)
            
            # Tenta descobrir o ID se foi enviado via body JSON (comum no create_session)
            if body_bytes:
                try:
                    body_json = json.loads(body_bytes)
                    session_id = body_json.get("sessionId", session_id)
                except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as e:
                    logger.debug("Não foi possível decodificar body como JSON: %s", e)
            
            # Delega a orquestração do bloqueio de fila para a porta de queue
            async with self.session_queue.acquire(session_id):
                response = await call_next(request)
                
                # Se o WSO2 mandou POST e a sessão já existia, faremos um Loopback enviando um PATCH real
                if response.status_code == 409:
                    logger.info("Detectado conflito 409 para session_id=%s. Executando fallback com PATCH...", session_id)
                    patch_url = f"/apps/{app_name}/users/{user_id}/sessions/{session_id}"
                    
                    headers = dict(request.headers)
                    # Limpa headers específicos que o httpx deve gerenciar automaticamente
                    headers.pop("content-length", None)
                    headers.pop("host", None)
                    
                    from httpx import ASGITransport
                    transport = ASGITransport(app=request.app)
                    base_url = str(request.base_url)
                    
                    async with httpx.AsyncClient(transport=transport, base_url=base_url, timeout=15.0) as client:
                        # O WSO2 envia um payload de Criação (só com sessionId).
                        # O ADK PATCH exige um payload de Atualização (com stateDelta).
                        # Injetamos o stateDelta vazio para evitar o erro 422 de validação.
                        patch_payload = {}
                        if body_bytes:
                            try:
                                patch_payload = json.loads(body_bytes)
                            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                                pass
                        
                        if "stateDelta" not in patch_payload:
                            patch_payload["stateDelta"] = {}
                            
                        patch_bytes = json.dumps(patch_payload).encode("utf-8")
                        
                        # Removemos o content-length porque alteramos o tamanho do body
                        headers.pop("content-length", None)
                        
                        patch_response = await client.patch(
                            patch_url, 
                            content=patch_bytes, 
                            headers=headers
                        )
                        
                        # Retorna a resposta real e atualizada que o ADK devolveu do PATCH
                        return Response(
                            content=patch_response.content,
                            status_code=patch_response.status_code,
                            media_type="application/json"
                        )
                
                return response
                
        return await call_next(request)
