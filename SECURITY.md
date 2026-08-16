# Security Policy

## Supported Version

Only the latest tagged `runtime-v1.*` release is supported.

## Reporting A Vulnerability

Use GitHub's private vulnerability reporting or open a private Security
Advisory in `ma-ho-git/ai-cps-public`. Do not publish credentials, broker
addresses or exploitable details in a public issue.

## Safety Boundary

This repository is a research and test environment. It is not a certified
industrial safety controller. The physical PLC, OPC UA integration and
Node-RED safety behavior remain an external black box. Physical command output
must only be enabled in a controlled laboratory environment with independent
PLC/Node-RED safety interlocks.

The default physical setup is diagnostic. Changing MQTT credentials, exposing
Node-RED or Mosquitto to an untrusted network, or enabling command output
requires a separate site security assessment.
