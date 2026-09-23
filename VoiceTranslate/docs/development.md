# Development

## Backend

Use Python 3.11 and the project environment:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Copy `backend/.env.example` to `backend/.env` and set a local `JWT_SECRET_KEY` and `DATABASE_URL`.

## Mobile

The Flutter foundation uses a configurable API URL:

```powershell
cd mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

## Scope rule

The current milestone stops at authentication and client foundations. WebSocket, audio, VAD, AI, and calling work must be implemented in later phases.
