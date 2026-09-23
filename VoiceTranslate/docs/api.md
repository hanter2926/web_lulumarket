# API

Base URL in local development: `http://localhost:8000`.

## Implemented endpoints

- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/users/me`

Authentication uses `Authorization: Bearer <access_token>` for protected requests.

## Not implemented yet

Contacts, calls, preferences, WebSocket calls, and translation endpoints are not currently exposed. Do not build clients against those paths yet.
