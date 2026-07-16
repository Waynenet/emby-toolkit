import unittest
from contextlib import contextmanager
import sys
import types
from unittest.mock import patch

connection_stub = types.ModuleType('database.connection')
connection_stub.get_db_connection = None
sys.modules['database.connection'] = connection_stub

from database.metadata_provider_db import (
    MEDIA_METADATA_SCHEMA_VERSION,
    has_initial_tmdb_metadata,
    load_emby_metadata,
    needs_metadata_backfill,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.current = None
        self.last_sql = ''
        self.last_params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.last_sql = sql
        self.last_params = params
        if 'SELECT 1 FROM media_metadata' in sql:
            self.current = self.rows.get('initial')
        elif "item_type='Episode'" in sql:
            self.current = self.rows.get('episode')
        elif "item_type='Movie'" in sql:
            self.current = self.rows.get('movie')
        elif "item_type='Series'" in sql:
            self.current = self.rows.get('series')
        elif 'FROM person_metadata' in sql:
            self.current = self.rows.get('people', [])

    def fetchone(self):
        return self.current if isinstance(self.current, dict) else None

    def fetchall(self):
        return self.current if isinstance(self.current, list) else []


class _Connection:
    def __init__(self, rows):
        self.cursor_value = _Cursor(rows)

    def cursor(self):
        return self.cursor_value


def _connection_factory(rows):
    @contextmanager
    def _connection():
        yield _Connection(rows)
    return _connection


class MetadataProviderDbTests(unittest.TestCase):
    def test_initial_snapshot_requires_current_metadata_schema_version(self):
        connection = _Connection({'initial': {'exists': 1}})

        @contextmanager
        def connection_factory():
            yield connection

        with patch('database.metadata_provider_db.get_db_connection', connection_factory):
            self.assertTrue(has_initial_tmdb_metadata('123', 'movie'))

        self.assertIn('metadata_schema_version >= %s', connection.cursor_value.last_sql)
        self.assertEqual(MEDIA_METADATA_SCHEMA_VERSION, connection.cursor_value.last_params[-1])

    def test_backfill_check_only_targets_in_library_old_schema_rows(self):
        connection = _Connection({'initial': {'exists': 1}})

        @contextmanager
        def connection_factory():
            yield connection

        with patch('database.metadata_provider_db.get_db_connection', connection_factory):
            self.assertTrue(needs_metadata_backfill('456', 'tv'))

        self.assertIn('in_library IS TRUE', connection.cursor_value.last_sql)
        self.assertIn('metadata_schema_version < %s', connection.cursor_value.last_sql)
        self.assertEqual(('456', 'Series', MEDIA_METADATA_SCHEMA_VERSION), connection.cursor_value.last_params)

    def test_movie_payload_contains_translated_people_and_four_images(self):
        rows = {
            'movie': {
                'tmdb_id': '123',
                'title': '测试电影',
                'original_title': 'Test Movie',
                'overview': '简介',
                'release_date': None,
                'release_year': 2026,
                'rating': 8.2,
                'actors_ready': True,
                'actors_json': [{'tmdb_id': 7, 'character': '主角', 'order': 0}],
                'directors_json': [{'id': 8, 'name': '测试导演', 'profile_path': '/director.jpg'}],
                'genres_json': [{'id': 1, 'name': '剧情'}],
                'tags_json': ['测试'],
                'production_companies_json': [{'name': '测试公司'}],
                'networks_json': [],
                'poster_path': '/poster.jpg',
                'backdrop_path': '/fanart.jpg',
                'logo_path': '/logo.png',
                'thumb_path': '/landscape.jpg',
            },
            'people': [{'tmdb_person_id': 7, 'primary_name': '测试演员', 'profile_path': '/actor.jpg'}],
        }
        with patch('database.metadata_provider_db.get_db_connection', _connection_factory(rows)):
            payload = load_emby_metadata('123', 'movie', 'Movie')

        self.assertTrue(payload['actors_ready'])
        self.assertEqual('测试演员', payload['people'][0]['name'])
        self.assertEqual('Director', payload['people'][1]['type'])
        self.assertTrue(payload['images']['primary'].endswith('/poster.jpg'))
        self.assertTrue(payload['images']['backdrop'].endswith('/fanart.jpg'))
        self.assertTrue(payload['images']['logo'].endswith('/logo.png'))
        self.assertTrue(payload['images']['thumb'].endswith('/landscape.jpg'))

    def test_missing_episode_uses_series_identity_without_fake_episode_tmdb_id(self):
        rows = {
            'episode': None,
            'series': {
                'tmdb_id': '456',
                'title': '测试剧集',
                'actors_ready': True,
                'actors_json': [],
                'directors_json': [],
                'genres_json': [],
                'tags_json': [],
                'production_companies_json': [],
                'networks_json': [],
            },
        }
        with patch('database.metadata_provider_db.get_db_connection', _connection_factory(rows)):
            payload = load_emby_metadata(
                '456', 'tv', 'Episode', season_number=2, episode_number=3,
            )

        self.assertEqual('Episode', payload['item_type'])
        self.assertEqual('', payload['tmdb_id'])
        self.assertEqual('456', payload['series_tmdb_id'])
        self.assertEqual(2, payload['season_number'])
        self.assertEqual(3, payload['episode_number'])
        self.assertFalse(payload['actors_ready'])


if __name__ == '__main__':
    unittest.main()
