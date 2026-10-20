"""Alembic environment. The code calls it with an open connection (``Database.migrate``)."""

from alembic import context

from fdeops.storage.db import Base

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    render_as_batch=connection.dialect.name == "sqlite",  # SQLite cannot ALTER most columns
    compare_type=True,
)
with context.begin_transaction():
    context.run_migrations()
