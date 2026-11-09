FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
# The control-panel HTML is embedded in server.py (self-contained build), so
# the image does NOT depend on a static/ directory being present in the
# build context. static/ and data/ are created at runtime.
RUN mkdir -p static data
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 16 --timeout 120 server:app"]
