# Usa uma imagem oficial enxuta e atualizada do Python
FROM python:3.12-slim

# Metadados
LABEL maintainer="Software Architect"
LABEL description="BigDataCorp Batch Processor"

# Define variáveis de ambiente (otimização do Python em container)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Define o diretório de trabalho
WORKDIR /app

# Copia os arquivos da aplicação
COPY src/ /app/src/
COPY tests/ /app/tests/

# Cria um usuário não-root por segurança (best practice SRE)
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Define o Entrypoint apontando para o orquestrador
# Permite que o container se comporte como um CLI
ENTRYPOINT ["python", "src/main.py"]
