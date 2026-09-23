# Infrastructure

This directory contains deployment configuration for the existing FastAPI backend. It does not create a second application or install AI models.

- `docker/`: CPU backend image configuration.
- `nginx/`: reverse-proxy example for HTTPS termination and API forwarding.
- `postgres/`: PostgreSQL deployment guidance.

Supply secrets and database URLs through the deployment environment, never through Dockerfiles or committed configuration.
