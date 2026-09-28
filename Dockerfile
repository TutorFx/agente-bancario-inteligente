FROM python:3.11

WORKDIR /app

# Instala as dependências do Python
COPY requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt


# Copia o código do projeto para o container
COPY . .

# O OpenShift roda o container com um UID aleatório do grupo root (GID 0): o grupo precisa
# de permissão de escrita em /app.
RUN chmod +x run.sh && chmod -R g+rwX /app

# Porta usada pelo docker-compose (o run.sh, sozinho, usa 8085)
EXPOSE 8000

CMD ["./run.sh"]
