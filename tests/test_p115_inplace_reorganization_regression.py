import ast
import re
import unittest
from pathlib import Path


def _load_reorganization_helpers():
    source_path = Path(__file__).parents[1] / 'handler' / 'p115_service.py'
    tree = ast.parse(source_path.read_text(encoding='utf-8'), filename=str(source_path))
    helper_names = {
        '_exclude_batch_conflict_rows',
        '_normalize_cached_local_path',
        '_is_same_cached_local_path',
    }
    helper_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in helper_names
    ]
    namespace = {'re': re}
    exec(
        compile(ast.Module(body=helper_nodes, type_ignores=[]), str(source_path), 'exec'),
        namespace,
    )
    return (
        namespace['_exclude_batch_conflict_rows'],
        namespace['_is_same_cached_local_path'],
    )


_exclude_batch_conflict_rows, _is_same_cached_local_path = _load_reorganization_helpers()


class P115InPlaceReorganizationRegressionTests(unittest.TestCase):
    def test_current_batch_files_are_not_existing_conflicts(self):
        rows = [
            {'id': 'episode-1', 'name': 'Show S01E01.mkv'},
            {'id': 'episode-2', 'name': 'Show S01E02.mkv'},
            {'id': 'old-version', 'name': 'Show S01E01 old.mkv'},
        ]

        remaining = _exclude_batch_conflict_rows(
            rows,
            {'episode-1', 'episode-2'},
        )

        self.assertEqual(
            remaining,
            [{'id': 'old-version', 'name': 'Show S01E01 old.mkv'}],
        )

    def test_unchanged_local_path_is_preserved(self):
        self.assertTrue(
            _is_same_cached_local_path(
                r'TV\Show\Season 01\Show S01E01.mkv',
                '/TV/Show/Season 01/Show S01E01.mkv',
            )
        )

    def test_changed_local_path_still_cleans_old_strm(self):
        self.assertFalse(
            _is_same_cached_local_path(
                'TV/Show/Season 01/Show S01E01.mkv',
                'TV/Show/Season 02/Show S02E01.mkv',
            )
        )


if __name__ == '__main__':
    unittest.main()
