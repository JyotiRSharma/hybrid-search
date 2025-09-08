FROM python:3.9-slim
WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir uv pipx && pipx install poetry==1.8.3 || true
# If not using poetry, copy requirements.txt and pip install instead.
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY app /app/app
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
