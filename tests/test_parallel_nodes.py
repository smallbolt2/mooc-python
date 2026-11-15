import sys
import threading
import time
import types
import unittest


# 调度测试不需要网络；在没有 requests 的运行环境中提供最小替身。
try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests = types.ModuleType('requests')

    class Session:
        def __init__(self):
            self.headers = {}
            self.cookies = {}

    class RequestException(Exception):
        pass

    requests.Session = Session
    requests.exceptions = types.SimpleNamespace(RequestException=RequestException)
    sys.modules['requests'] = requests

from mooc.user import User


class ParallelNodeTests(unittest.TestCase):
    def make_user(self, nodes):
        user = User('https://example.test', 0, 'tester', 'secret')
        user.running = True
        user.token = 'test-token'
        user.get_chapters = lambda course_id: [{'idx': 1, 'name': '第一章', 'nodeList': nodes}]
        return user

    @staticmethod
    def course():
        return {'id': 100, 'name': '测试课程'}

    def test_parallel_mode_runs_all_nodes_at_once(self):
        nodes = [{'id': index, 'name': f'节点{index}', 'tabVideo': True} for index in range(3)]
        user = self.make_user(nodes)
        barrier = threading.Barrier(3)
        started = []

        def study_node(node):
            started.append(node['id'])
            barrier.wait(timeout=2)
            return True

        user.study_node = study_node
        user.check_node_status = lambda node: self.fail('全部并行模式不应预先检查锁定状态')

        result = user.study_course(
            self.course(), parallel_nodes=True, node_mode='parallel', node_limit=3
        )

        self.assertTrue(result)
        self.assertCountEqual(started, [0, 1, 2])

    def test_auto_mode_runs_unlocked_course_at_once(self):
        nodes = [{
            'id': index + 1,
            'name': f'节点{index}',
            'tabVideo': True,
            'nodeLock': 0,
            'videoState': 0
        } for index in range(3)]
        user = self.make_user(nodes)
        barrier = threading.Barrier(3)
        # 与平台的新节点一致：还没有学习记录时 study_total 返回空列表。
        user.get_node_progress = lambda node_id: {'study_total': []}
        user.study_node = lambda node: barrier.wait(timeout=2) is not None or True

        result = user.study_course(
            self.course(), parallel_nodes=True, node_mode='auto', node_limit=3
        )

        self.assertTrue(result)

    def test_empty_progress_does_not_unlock_node_with_prerequisite(self):
        user = self.make_user([])
        user.get_node_progress = lambda node_id: {'study_total': []}
        node = {
            'id': 1,
            'name': '前置受限节点',
            'tabVideo': True,
            'nodeLock': 1,
            'videoState': 0
        }

        self.assertEqual(user.check_node_status(node), 'error')

    def test_auto_mode_waits_for_prerequisite_before_locked_node(self):
        nodes = [{'id': index, 'name': f'节点{index}', 'tabVideo': True} for index in range(3)]
        user = self.make_user(nodes)
        states = {0: 'unlocked', 1: 'unlocked', 2: 'locked'}
        first_batch = threading.Barrier(2)
        finished = set()
        started = []
        lock = threading.Lock()

        user.check_node_status = lambda node: states[node['id']]

        def study_node(node):
            node_id = node['id']
            with lock:
                started.append(node_id)
                if node_id == 2:
                    self.assertEqual(finished, {0, 1})
            if node_id in (0, 1):
                first_batch.wait(timeout=2)
            time.sleep(0.02)
            with lock:
                finished.add(node_id)
                states[node_id] = 'completed'
                if finished == {0, 1}:
                    states[2] = 'unlocked'
            return True

        user.study_node = study_node
        result = user.study_course(
            self.course(), parallel_nodes=True, node_mode='auto', node_limit=3
        )

        self.assertTrue(result)
        self.assertEqual(started[-1], 2)
        self.assertCountEqual(started[:2], [0, 1])

    def test_sequential_mode_preserves_course_order(self):
        nodes = [{'id': index, 'name': f'节点{index}', 'tabVideo': True} for index in range(3)]
        user = self.make_user(nodes)
        started = []
        user.study_node = lambda node: started.append(node['id']) is None
        user.check_node_status = lambda node: self.fail('严格顺序模式不需要批量状态检查')

        result = user.study_course(
            self.course(), parallel_nodes=True, node_mode='sequential', node_limit=3
        )

        self.assertTrue(result)
        self.assertEqual(started, [0, 1, 2])

    def test_nested_video_nodes_are_flattened_without_duplicates(self):
        user = self.make_user([])
        chapters = [{
            'nodeList': [{
                'id': 1,
                'name': '父节点',
                'tabVideo': True,
                'children': [
                    {'id': 2, 'name': '子节点', 'tabVideo': True},
                    {'id': 2, 'name': '重复子节点', 'tabVideo': True},
                    {'id': 3, 'name': '文档节点', 'tabVideo': False}
                ]
            }]
        }]

        nodes = user._get_video_nodes(chapters)

        self.assertEqual([node['id'] for node in nodes], [1, 2])

    def test_stopped_node_returns_before_starting_monitor(self):
        user = self.make_user([])
        user.running = False

        result = user.study_node({'id': 1, 'name': '节点1', 'tabVideo': True})

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
