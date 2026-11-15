import unittest
from unittest.mock import Mock, patch

import app as app_module


class PreviewUser:
    def __init__(self):
        self.current_status = '登录成功'
        self.running = False
        self.session = Mock()

    def login(self):
        return True

    def get_courses(self):
        return [{
            'id': 101,
            'name': '课程A',
            'progress': 0.25,
            'progress1': '25%'
        }]


class ParallelApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.config = {
            'global': {'server': ':10086', 'limit': 1},
            'users': [{
                'base_url': 'https://one.example.test',
                'school_id': 0,
                'username': 'tester',
                'password': 'secret'
            }]
        }
        self.user_key = app_module.get_config_user_key(self.config['users'][0])
        config_patch = patch.object(app_module, 'load_config', return_value=self.config)
        config_patch.start()
        self.addCleanup(config_patch.stop)

    def test_course_preview_returns_only_course_fields(self):
        preview_user = PreviewUser()
        with patch.object(app_module, 'create_configured_user', return_value=preview_user):
            response = self.client.post('/api/parallel/courses', json={'username': 'tester'})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['courses'], [{
            'id': '101',
            'name': '课程A',
            'progress': 0.25,
            'progress_text': '25%'
        }])
        self.assertFalse(preview_user.running)

    def test_start_passes_per_course_modes_and_limits(self):
        with patch.object(app_module, 'launch_user') as launch:
            response = self.client.post('/api/parallel/start', json={
                'username': 'tester',
                'user_key': self.user_key,
                'course_ids': [101, '102', 101],
                'course_modes': {'101': 'parallel', '102': 'sequential'},
                'node_limit': 6,
                'course_limit': 2
            })

            self.assertTrue(response.get_json()['success'])
            username, runner = launch.call_args[0]
            self.assertEqual(username, self.user_key)
            user = Mock()
            runner(user)
            user.run.assert_called_once_with(
                parallel_nodes=True,
                course_ids=['101', '102'],
                course_modes={'101': 'parallel', '102': 'sequential'},
                node_limit=6,
                course_limit=2
            )

    def test_start_rejects_invalid_mode(self):
        with patch.object(app_module, 'launch_user') as launch:
            response = self.client.post('/api/parallel/start', json={
                'username': 'tester',
                'course_ids': [101],
                'course_modes': {'101': 'ignore_prerequisites'},
                'node_limit': 3,
                'course_limit': 1
            })

        self.assertFalse(response.get_json()['success'])
        launch.assert_not_called()

    def test_start_rejects_out_of_range_limits(self):
        with patch.object(app_module, 'launch_user') as launch:
            response = self.client.post('/api/parallel/start', json={
                'username': 'tester',
                'course_ids': [101],
                'course_modes': {},
                'node_limit': 21,
                'course_limit': 1
            })

        self.assertFalse(response.get_json()['success'])
        launch.assert_not_called()

    def test_start_requires_a_course(self):
        response = self.client.post('/api/parallel/start', json={
            'username': 'tester',
            'course_ids': [],
            'course_modes': {}
        })

        self.assertFalse(response.get_json()['success'])


if __name__ == '__main__':
    unittest.main()
