FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    AUTO_OPEN_BROWSER=0

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicación completa
COPY . .

# Exponer el puerto
EXPOSE 8000

# Ejecutar el servidor
CMD ["python", "run.py"]
