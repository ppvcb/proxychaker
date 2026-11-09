FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
# Control-panel HTML — must be copied so Railway serves the latest UI
# (the Generate button, key display, copy buttons etc.).
COPY static/ ./static/
# data/ is created at runtime (api_key, proxies.json)
RUN mkdir -p data
# PORT is injected by Railway; default to 8080 for plain Docker use.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 16 --timeout 120 server:app"]
