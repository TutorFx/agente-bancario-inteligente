import abc

class IEventPublisher(abc.ABC):
    """
    Interface (Port) para publicação de eventos do sistema, permitindo que a
    camada de domínio dissemine eventos sem conhecer detalhes de mensageria ou HTTP.
    """

    @abc.abstractmethod
    async def publish_flow_completed(self, thread_id: str, flow_id: str) -> bool:
        """
        Publica um evento indicando que o fluxo de atendimento foi concluído.
        
        Args:
            thread_id (str): Identificador único da sessão/conversa do usuário.
            flow_id (str): Identificador do fluxo (ex: "flow_banco_agil").
            
        Returns:
            bool: True se o evento foi despachado com sucesso, False caso contrário.
        """
        pass

    @abc.abstractmethod
    async def publish_flow_started(self, thread_id: str, flow_id: str, sender_id: str, sender_name: str) -> bool:
        """
        Publica um evento indicando que o fluxo de atendimento foi iniciado.
        
        Args:
            thread_id (str): Identificador único da sessão/conversa do usuário.
            flow_id (str): Identificador do fluxo (ex: "flow_banco_agil").
            sender_id (str): ID ou telefone do usuário interagindo.
            sender_name (str): Nome do usuário interagindo.
            
        Returns:
            bool: True se o evento foi despachado com sucesso, False caso contrário.
        """
        pass
