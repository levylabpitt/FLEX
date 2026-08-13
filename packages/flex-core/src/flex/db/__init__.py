"""flex.db (FLEX v2)."""

__version__ = "2.0.0a1"

#: DB backend name -> "module:Class" reference.
DB_BACKENDS: dict[str, str] = {
    "sqlite": "flex.db.sqlite:SQLiteStore",
    "postgres": "flex.db.postgres:PostgresStore",
}
