"""Metadata store backends."""

DB_BACKENDS: dict[str, str] = {
    "sqlite": "flex.db.sqlite:SQLiteStore",
    "postgres": "flex.db.postgres:PostgresStore",
}
