FROM python:3.10-slim@sha256:63669fd2563fa90b0442fa7b568e66e3667755636cda086d7bcaaa895f66fe39
ARG SOURCE_REVISION=unknown
ARG RELEASE_VERSION=development
LABEL org.opencontainers.image.source="https://github.com/ma-ho-git/ai-cps-public" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${RELEASE_VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

WORKDIR /app
COPY training/vgr/requirements-training.lock /app/requirements-training.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements-training.lock \
    && pip check

COPY training/vgr/train.py /app/train.py
COPY training/lstm_common.py /app/training/lstm_common.py

CMD ["python", "/app/train.py", "--config", "/configs/train_vgr.json"]
