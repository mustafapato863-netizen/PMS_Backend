from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_recovered_migration_graph_has_one_head() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["e3b8c1d4f920"]
    assert scripts.get_revision("c7e9a4b2d610").down_revision == "7f3c9a1d2e40"
    assert scripts.get_revision("a2d91f4c1b7e") is not None
    assert scripts.get_revision("b1f3d8e7a901") is not None
    assert scripts.get_revision("d4e8b7c1a920") is not None
    assert scripts.get_revision("f6c2a9d4e810").down_revision == (
        "a2d91f4c1b7e",
        "b1f3d8e7a901",
        "d4e8b7c1a920",
    )
