# Troubleshooting

## Pylance cannot resolve imports

Select `backend/.venv/Scripts/python.exe` as the workspace interpreter. Install backend dependencies into that environment only.

## API does not start

Run from `backend` so `app` is on the import path:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Database connection errors

Check `DATABASE_URL`, ensure PostgreSQL is reachable, and run `alembic upgrade head`. Authentication tests use SQLite and do not need PostgreSQL.

## Mobile cannot reach localhost

Android emulators use `http://10.0.2.2:8000`. Physical devices need a configurable LAN address and firewall access. Do not use a production URL in source code.

## AI expectations

Whisper, SeamlessM4T, XTTS-v2, VAD, audio streaming, and WebSocket calls are not implemented in the current milestone.
