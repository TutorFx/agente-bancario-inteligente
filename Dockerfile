FROM python:3.11

WORKDIR /app

# Instala as dependências do Python
COPY requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt


# Copia o código do projeto para o container
COPY . .

# Torna o script run.sh executável e garante compatibilidade de permissões com o OpenShift.
# O OpenShift executa o container com um UID aleatório não-privilegiado pertencente ao grupo root (GID 0).
RUN chmod +x run.sh && chmod -R g+rwX /app

# Exprime a porta 8000 usada pelo servidor API do ADK (FastAPI)
EXPOSE 8000

CMD ["./run.sh"]
