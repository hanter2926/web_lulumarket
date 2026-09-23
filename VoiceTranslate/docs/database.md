# Database

## Implemented

The backend uses SQLAlchemy 2.x async sessions and PostgreSQL configuration through `DATABASE_URL`. Alembic revisions create users, devices, contacts, calls, call participants, translation sessions, translation chunks, and user preferences.

UUID primary keys, timestamps, foreign keys, indexes, uniqueness constraints, and cascade relationships are defined. Raw voice recordings are not stored.

Run migrations from `backend`:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

Tests use an in-memory SQLite database and do not require PostgreSQL.

## Planned

Production connection pooling, backups, observability, and migration rollout policy will be documented during deployment hardening.
