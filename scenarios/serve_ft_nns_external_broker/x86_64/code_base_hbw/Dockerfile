FROM python:3.12.3-slim-bookworm@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63
ARG SOURCE_REVISION=unknown
ARG RELEASE_VERSION=development
LABEL org.opencontainers.image.source="https://github.com/ma-ho-git/ai-cps-runtime" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${RELEASE_VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
WORKDIR /codeBase/code_base_hbw

COPY code_base_hbw/requirements.txt ./requirements.txt
COPY code_base_common/requirements-runtime.lock /codeBase/code_base_common/requirements-runtime.lock
RUN pip install --no-cache-dir --require-hashes -r /codeBase/code_base_common/requirements-runtime.lock \
    && pip check

COPY code_base_common/mqtt_runtime.py /codeBase/code_base_common/mqtt_runtime.py
COPY code_base_common/model_profiles.py /codeBase/code_base_common/model_profiles.py
COPY code_base_hbw/mqtt_infer.py ./mqtt_infer.py

CMD ["python", "/codeBase/code_base_hbw/mqtt_infer.py"]
