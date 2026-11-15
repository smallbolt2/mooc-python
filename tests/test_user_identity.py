import copy
import unittest
from unittest.mock import patch

import app as app_module


def account(base_url, password='secret'):
    return {
        'base_url': base_url,
        'school_id': 0,
        'username': 'same-user',
        'password': password
    }


class UserIdentityTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.site_a = account('https://a.example.test')
        self.site_b = account('https://b.example.test')
        self.key_a = app_module.get_config_user_key(self.site_a)
        self.key_b = app_module.get_config_user_key(self.site_b)
        self.assertNotEqual(self.key_a, self.key_b)

    def config(self, users):
        return {'global': {'server': ':10086', 'limit': 1}, 'users': users}

    def test_save_allows_same_username_on_another_site(self):
        config = self.config([copy.deepcopy(self.site_a)])
        with patch.object(app_module, 'load_config', return_value=config), \
                patch.object(app_module, 'write_config') as write:
            response = self.client.post('/api/save_config', json={
                **self.site_b,
                'limit': 1
            })

        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user_key'], self.key_b)
        self.assertEqual(len(config['users']), 2)
        self.assertEqual({u['base_url'] for u in config['users']}, {
            'https://a.example.test', 'https://b.example.test'
        })
        write.assert_called_once_with(config)

    def test_save_updates_only_matching_site(self):
        config = self.config([copy.deepcopy(self.site_a), copy.deepcopy(self.site_b)])
        with patch.object(app_module, 'load_config', return_value=config), \
                patch.object(app_module, 'write_config'):
            response = self.client.post('/api/save_config', json={
                **account('https://b.example.test', password='new-password'),
                'user_key': self.key_b,
                'limit': 1
            })

        self.assertTrue(response.get_json()['success'])
        self.assertEqual(config['users'][0]['password'], 'secret')
        self.assertEqual(config['users'][1]['password'], 'new-password')

    def test_delete_removes_only_requested_site(self):
        config = self.config([copy.deepcopy(self.site_a), copy.deepcopy(self.site_b)])
        with patch.object(app_module, 'load_config', return_value=config), \
                patch.object(app_module, 'write_config'), \
                patch.dict(app_module.users, clear=True), \
                patch.dict(app_module.user_threads, clear=True):
            response = self.client.post('/api/users/delete', json={
                'username': 'same-user',
                'user_key': self.key_b
            })

        self.assertTrue(response.get_json()['success'])
        self.assertEqual(len(config['users']), 1)
        self.assertEqual(app_module.get_config_user_key(config['users'][0]), self.key_a)

    def test_user_list_exposes_distinct_keys_and_sites(self):
        config = self.config([copy.deepcopy(self.site_a), copy.deepcopy(self.site_b)])
        with patch.object(app_module, 'load_config', return_value=config):
            response = self.client.get('/api/users')

        users = response.get_json()
        self.assertEqual({u['user_key'] for u in users}, {self.key_a, self.key_b})
        self.assertEqual({u['site'] for u in users}, {'a.example.test', 'b.example.test'})

    def test_legacy_username_request_is_rejected_when_ambiguous(self):
        config = self.config([copy.deepcopy(self.site_a), copy.deepcopy(self.site_b)])
        with patch.object(app_module, 'load_config', return_value=config):
            response = self.client.post('/api/users/delete', json={'username': 'same-user'})

        self.assertFalse(response.get_json()['success'])
        self.assertIn('多个网站', response.get_json()['message'])

    def test_start_uses_requested_site_identity(self):
        config = self.config([copy.deepcopy(self.site_a), copy.deepcopy(self.site_b)])
        with patch.object(app_module, 'load_config', return_value=config), \
                patch.object(app_module, 'get_code', return_value='tt7z'), \
                patch.object(app_module, 'launch_user') as launch:
            response = self.client.post('/api/start', json={'user_key': self.key_b})

        self.assertTrue(response.get_json()['success'])
        self.assertEqual(response.get_json()['user_key'], self.key_b)
        self.assertEqual(launch.call_args[0][0], self.key_b)


if __name__ == '__main__':
    unittest.main()
