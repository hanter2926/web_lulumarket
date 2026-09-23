# VoiceTranslate Backend

FastAPI backend for the VoiceTranslate real-time translation service.

## Local development

Use Python 3.11, create a virtual environment, install `requirements.txt`, copy `.env.example` to `.env`, and run:

```powershell
python -m uvicorn app.main:app --reload
```

The health endpoints are available at `/health`, `/health/live`, and `/health/ready`.
