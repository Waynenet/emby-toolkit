import unittest
from unittest.mock import Mock, patch

from handler import emby
from handler import shared_subscription_service
from routes import webhook


class _Response:
    def __init__(self, items):
        self._items = items

    def raise_for_status(self):
        return None

    def json(self):
        return {"Items": self._items}


class ActiveEmbyIngestTests(unittest.TestCase):
    @patch.object(emby.emby_client, "get")
    def test_get_item_by_path_requires_exact_path(self, mock_get):
        expected = "/media/tv/Show/Season 01/Show S01E01.strm"
        mock_get.return_value = _Response([
            {"Id": "wrong", "Path": expected + ".bak", "Type": "Episode"},
            {"Id": "right", "Path": expected, "Type": "Episode"},
        ])

        item = emby.get_emby_item_by_path(expected, "http://emby", "key", "user")

        self.assertEqual("right", item["Id"])
        self.assertEqual(expected, mock_get.call_args.kwargs["params"]["Path"])

    @patch.object(emby.time, "sleep")
    @patch.object(emby, "get_emby_item_by_path")
    def test_wait_for_items_retries_until_id_exists(self, mock_lookup, mock_sleep):
        path = "/media/movies/Movie/Movie.strm"
        mock_lookup.side_effect = [None, {"Id": "42", "Path": path, "Type": "Movie"}]

        found = emby.wait_for_emby_items_by_path(
            [path], "http://emby", "key", retry_delays=(0, 0.25)
        )

        self.assertEqual("42", found[path]["Id"])
        mock_sleep.assert_called_once_with(0.25)

    def test_active_episode_ids_are_grouped_by_series(self):
        processor = Mock()
        processor.emby_url = "http://emby"
        processor.emby_api_key = "key"
        processor.emby_user_id = "user"
        processor.processed_items_cache = {}
        items = [
            {"Id": "ep1", "Type": "Episode", "Name": "Episode 1", "SeriesId": "series1"},
            {"Id": "ep2", "Type": "Episode", "Name": "Episode 2", "SeriesId": "series1"},
        ]

        with patch.object(webhook.extensions, "media_processor_instance", processor), \
             patch.object(webhook.emby, "get_emby_item_details", return_value={"Name": "Show"}), \
             patch.object(webhook, "_submit_webhook_media_task") as submit:
            webhook.dispatch_active_emby_items(items)

        submit.assert_called_once()
        kwargs = submit.call_args.kwargs
        self.assertEqual("series1", kwargs["item_id"])
        self.assertEqual(["ep1", "ep2"], kwargs["new_episode_ids"])
        self.assertTrue(kwargs["is_new_item"])

    @patch.object(shared_subscription_service, "shared_center_enabled", return_value=True)
    @patch.object(shared_subscription_service, "_call_rapid_method")
    @patch.object(shared_subscription_service.P115Service, "get_client", return_value=Mock())
    def test_no_available_holder_is_retriable_with_retry_after(
        self, _mock_p115, mock_rapid, _mock_center_enabled
    ):
        mock_rapid.return_value = {
            "status": 7,
            "sign_key": "key",
            "sign_check": "1-2",
        }
        center = Mock()
        center.create_rapid_sign_job.side_effect = RuntimeError(
            "409 {'reason': 'no_available_holder', 'retry_after': 12}"
        )

        with patch.object(shared_subscription_service, "SharedCenterClient", return_value=center):
            result = shared_subscription_service.rapid_save_file({
                "sha1": "A" * 40,
                "size": 1024,
                "file_name": "episode.mkv",
                "source_kind": "logical_episode",
                "source_id": "episode-1",
            }, target_cid="target")

        self.assertFalse(result["ok"])
        self.assertFalse(result["no_retry"])
        self.assertFalse(result["abort_transfer"])
        self.assertEqual(12, result["retry_after"])


if __name__ == "__main__":
    unittest.main()
