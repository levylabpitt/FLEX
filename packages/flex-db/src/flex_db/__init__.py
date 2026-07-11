"""flex_db (FLEX v2)."""

__version__ = "2.0.0a1"

#: DB backend name -> "module:Class" reference.
DB_BACKENDS: dict[str, str] = {
    "sqlite": "flex_db.sqlite:SQLiteStore",
    "postgres": "flex_db.postgres:PostgresStore",
}
