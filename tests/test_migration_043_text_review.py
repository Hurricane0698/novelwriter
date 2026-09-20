import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_existing_text_and_settings_survive_upgrade_and_downgrade(tmp_path):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/043_add_text_review_sources.py"
    spec = importlib.util.spec_from_file_location("migration_043", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'book.db'}")
    with engine.begin() as connection:
        for table in ["continuations", *module.WORLD_TABLES]:
            connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, content TEXT)")
            connection.exec_driver_sql(f"INSERT INTO {table} VALUES (1, '原有内容')")
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        module.upgrade()
        assert connection.exec_driver_sql("SELECT content, edited_content FROM continuations").one() == ("原有内容", None)
        for table in module.WORLD_TABLES:
            assert connection.exec_driver_sql(f"SELECT content, source_metadata FROM {table}").one() == ("原有内容", None)
        module.downgrade()
        assert connection.exec_driver_sql("SELECT content FROM continuations").scalar() == "原有内容"
