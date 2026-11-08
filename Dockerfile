FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
# Copy static panel files (copy individual files to avoid COPY failures)
COPY static/ ./static/
# data/ is created at runtime (api_key, proxies.json)
RUN mkdir -p data
ENV PORT=8080
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "8", "--timeout", "120", "server:app"]
