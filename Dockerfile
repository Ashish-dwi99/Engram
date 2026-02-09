FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY engram/ engram/
RUN pip install --no-cache-dir ".[api]"
EXPOSE 8100
ENV ENGRAM_DATA_DIR=/data
VOLUME /data
CMD ["engram-api", "--host", "0.0.0.0", "--port", "8100"]
