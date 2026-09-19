FROM python:3.12-slim

RUN groupadd -g 1000 lucca && useradd -u 1000 -g lucca -m lucca
RUN mkdir -p /workspace /tmp && chown -R lucca:lucca /workspace /tmp

WORKDIR /workspace
COPY docker/toolsrv /opt/toolsrv
COPY src/lucca /opt/lucca
ENV PYTHONPATH="/opt:/opt/toolsrv"
ENV LUCCA_SANDBOX_CONTAINER="1"

RUN touch /opt/lucca/.sandbox_container && chown lucca:lucca /opt/lucca/.sandbox_container

RUN echo '#!/bin/sh\nexec python3 -m server "$@"' > /usr/local/bin/lucca-toolsrv && \
    chmod +x /usr/local/bin/lucca-toolsrv

USER lucca:lucca
