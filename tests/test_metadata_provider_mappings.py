import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch


connection_stub = types.ModuleType("database.connection")
connection_stub.get_db_connection = None
sys.modules["database.connection"] = connection_stub

config_manager_stub = types.ModuleType("config_manager")
config_manager_stub.APP_CONFIG = {}
sys.modules["config_manager"] = config_manager_stub

settings_db_stub = types.ModuleType("database.settings_db")
settings_db_stub.get_setting = None
sys.modules["database.settings_db"] = settings_db_stub

import constants
from database.metadata_provider_db import load_emby_metadata


class _Cursor:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql, _params):
        return None

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, row):
        self.cursor_value = _Cursor(row)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_value


class MetadataProviderMappingTests(unittest.TestCase):
    def test_only_mapped_chinese_labels_and_us_rating_are_returned(self):
        row = {
            "tmdb_id": "1669",
            "item_type": "Movie",
            "title": "猎杀红色十月",
            "custom_rating": "青少年",
            "official_rating_json": {"US": "PG-13"},
            "actors_ready": False,
            "keywords_json": [
                {"id": 470, "name": "spy"},
                {"id": 818, "name": "based on novel or book"},
            ],
            "production_companies_json": [
                {"id": 4, "name": "Paramount Pictures"},
                {"id": 264010, "name": "Mace Neufeld/Jerry Sherlock Productions"},
            ],
            "networks_json": [],
            "genres_json": [],
        }
        mappings = {
            "keyword_mapping": [{"label": "间谍", "en": ["spy"], "ids": [470]}],
            "studio_mapping": [
                {"label": "派拉蒙", "en": ["Paramount Pictures"], "company_ids": [4]},
            ],
        }

        @contextmanager
        def connection_factory():
            yield _Connection(row)

        flags = {
            constants.CONFIG_OPTION_KEYWORD_TO_TAGS: True,
            constants.CONFIG_OPTION_STUDIO_TO_CHINESE: True,
        }
        with patch.dict(config_manager_stub.APP_CONFIG, flags, clear=False), \
                patch.object(settings_db_stub, "get_setting", side_effect=lambda name: mappings.get(name)), \
                patch("database.metadata_provider_db.get_db_connection", connection_factory):
            payload = load_emby_metadata("1669", "movie", "Movie")

        self.assertEqual(["间谍"], payload["tags"])
        self.assertEqual(["派拉蒙"], payload["studios"])
        self.assertEqual("PG-13", payload["official_rating"])


if __name__ == "__main__":
    unittest.main()
