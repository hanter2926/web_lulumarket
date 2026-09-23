# Deployment

## Current backend container

`backend/Dockerfile` builds a Python 3.11 CPU image, installs the declared backend dependencies, copies the FastAPI app and Alembic files, and serves port 8000. It does not download AI models.

Build and run with environment variables supplied at runtime:

```powershell
docker build -f backend/Dockerfile -t voicetranslate-backend backend
docker run --env-file backend/.env -p 8000:8000 voicetranslate-backend
```

Run migrations as a deployment step before accepting traffic. Health probes should call `/health/live` for process liveness and `/health/ready` for readiness.

## Production concerns

Use managed PostgreSQL, HTTPS termination, secret injection, restricted CORS origins, resource limits, and non-root container execution. GPU workers and model images are future work and are intentionally not included here.
