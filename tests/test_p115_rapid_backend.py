import unittest
from unittest.mock import patch

from handler.p115_service import P115Service
from handler.shared_subscription_service import _retry_rapid_with_center_sign


class _RapidClient:
    def __init__(self, response):
        self.calls = []
        self.response = response

    def rapid_upload(self, payload):
        self.calls.append(payload)
        return dict(self.response)


class _CenterClient:
    def create_rapid_sign_job(self, payload):
        return {'job_id': 'job-1'}

    def wait_rapid_sign_job(self, job_id, timeout):
        return {'status': 'done', 'sign_val': 'B' * 40}


class P115RapidBackendTest(unittest.TestCase):
    def test_cookie_signed_retry_does_not_fall_back_to_openapi(self):
        cookie = _RapidClient({'state': False, 'status': 0, 'error_msg': 'expired sign'})
        openapi = _RapidClient({'state': True, 'status': 2})

        with (
            patch.object(P115Service, 'get_cookie_client', return_value=cookie),
            patch.object(P115Service, 'get_openapi_client', return_value=openapi),
            patch('handler.p115_service.get_115_api_priority', return_value='cookie'),
            patch('handler.p115_service.time.sleep'),
            patch('handler.shared_subscription_service.logger.trace', create=True),
        ):
            p115 = P115Service.get_client()
            p115._rate_limit = lambda: None
            result = _retry_rapid_with_center_sign(
                client=_CenterClient(),
                p115=p115,
                file_info={'source_kind': 'movie', 'source_id': 'source-1'},
                target_cid='123',
                sha1='A' * 40,
                size=1024,
                file_name='movie.mkv',
                rapid_meta={'preid': 'C' * 40},
                first_resp={
                    'state': False,
                    '_rapid_sign_required': True,
                    '_rapid_sign_backend': 'cookie',
                    '_rapid_sign_key': 'sign-key',
                    '_rapid_sign_check': '0-1',
                },
            )

        self.assertFalse(result['ok'])
        self.assertEqual(len(cookie.calls), 1)
        self.assertEqual(len(openapi.calls), 0)
        self.assertEqual(cookie.calls[0]['sign_key'], 'sign-key')
        self.assertEqual(cookie.calls[0]['sign_val'], 'B' * 40)


if __name__ == '__main__':
    unittest.main()
