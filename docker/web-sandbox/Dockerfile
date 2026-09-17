FROM python:3.12-slim

RUN groupadd -g 1000 lucca && useradd -u 1000 -g lucca -m lucca
RUN pip install --no-cache-dir httpx trafilatura

COPY docker/toolsrv /opt/toolsrv
COPY src/lucca /opt/lucca
ENV PYTHONPATH="/opt:/opt/toolsrv"

RUN echo '#!/bin/sh\nexec python3 -m server "$@"' > /usr/local/bin/lucca-toolsrv && \
    chmod +x /usr/local/bin/lucca-toolsrv

USER lucca:lucca
