FROM nodered/node-red:4.1.11-22@sha256:c8657806d6099d09896aabe5bb2ab8439534caccf52179ac9166060e229c9cf7
ARG SOURCE_REVISION=unknown
ARG RELEASE_VERSION=development
LABEL org.opencontainers.image.source="https://github.com/ma-ho-git/ai-cps-runtime" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${RELEASE_VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

USER root
COPY --chown=node-red:node-red node_red/dashboard_runtime/package.json node_red/dashboard_runtime/package-lock.json /opt/ai-cps-dashboard/
RUN npm ci --omit=dev --prefix /opt/ai-cps-dashboard \
    && mkdir -p /usr/src/node-red/node_modules/@flowfuse \
    && ln -s /opt/ai-cps-dashboard/node_modules/@flowfuse/node-red-dashboard \
      /usr/src/node-red/node_modules/@flowfuse/node-red-dashboard
COPY --chown=node-red:node-red node_red /opt/ai-cps-node-red
COPY --chown=node-red:node-red test_payloads/live_plc_trace /opt/ai-cps-node-red/data/live_plc_trace
COPY --chown=node-red:node-red test_payloads/live_plc_full_storage_attempt /opt/ai-cps-node-red/data/live_plc_full_storage_attempt
COPY --chown=node-red:node-red test_payloads/live_plc_full_storage_process_guard /opt/ai-cps-node-red/data/live_plc_full_storage_process_guard
RUN chmod 0755 /opt/ai-cps-node-red/entrypoint.sh
USER node-red

ENTRYPOINT ["/opt/ai-cps-node-red/entrypoint.sh"]
CMD ["run"]
