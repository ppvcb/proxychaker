FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
# The control-panel HTML is embedded in server.py (self-contained build).
# static/ and data/ directories are created at runtime; no external file copy needed.
RUN mkdir -p static data
ENV PORT=8080
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "8", "--timeout", "120", "server:app"]
