FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir 'numpy==2.5.4' 'psycopg[binary]==3.3.8' 'typing-extensions==4.16.0'
COPY experiment /app/experiment
CMD ["python", "-m", "experiment.harness", "serve", "--host", "0.0.0.0", "--port", "8765"]
