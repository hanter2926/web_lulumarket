# PostgreSQL

The backend expects PostgreSQL through `DATABASE_URL`, for example:

`postgresql+psycopg://user:password@postgres:5432/voicetranslate`

Provide credentials through a secret manager or runtime environment. Do not commit them. Run Alembic migrations from the backend container before serving traffic:

```text
alembic upgrade head
```

Backups, TLS, storage sizing, and high availability are deployment responsibilities and are not automated by this repository yet.
