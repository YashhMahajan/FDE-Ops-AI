def test_hosted_postgres_urls_get_the_driver_name() -> None:
    from fdeops.storage.db import normalize_url

    assert normalize_url("postgres://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert normalize_url("postgresql://u@h/d") == "postgresql+psycopg://u@h/d"
    assert normalize_url("postgresql+psycopg://u@h/d") == "postgresql+psycopg://u@h/d"
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"
