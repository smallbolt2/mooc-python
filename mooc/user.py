import requests
import time
import logging
import random
from datetime import datetime
import os
import json
import base64
from typing import List, Dict, Optional
import threading
from queue import Queue
import concurrent.futures
import io
import contextlib


def create_ocr():
    """静默创建 ddddocr 实例，避免导入时输出广告信息。"""
    try:
        import ddddocr
        if getattr(ddddocr.DdddOcr, '_mooc_silent_patch', False) is False:
            original_init = ddddocr.DdddOcr.__init__

            def silent_init(self, *args, **kwargs):
                kwargs.setdefault('show_ad', False)
                return original_init(self, *args, **kwargs)

            ddddocr.DdddOcr.__init__ = silent_init
            ddddocr.DdddOcr._mooc_silent_patch = True
    except Exception:
        pass

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import ddddocr
    return ddddocr.DdddOcr(show_ad=False)


class User:
    def __init__(self, base_url: str, school_id: int, username: str, password: str, study_limit: int = 3):
        # 确保 base_url 格式正确
        self.base_url = base_url.rstrip('/')
        if self.base_url.endswith('/user/login'):
            self.base_url = self.base_url[:self.base_url.rfind('/user/login')]
        if self.base_url.endswith('/user'):
            self.base_url = self.base_url[:self.base_url.rfind('/user')]
        
        self.school_id = school_id
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.running = False
        self.current_status = "未启动"
        self.current_course = None
        self.current_video = None
        self.token = None
        self.setup_logging()
        
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Mobile Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json, text/plain, */*',
            'Origin': self.base_url,
            'Referer': f"{self.base_url}/user/login"
        })
        
        self.logger.info(f"初始化完成，base_url: {self.base_url}")
        self.study_limit = study_limit  # 同时学习的课程数量限制
        self.study_queue = Queue()  # 课程学习队列
        self.study_threads = []  # 学习线程列表
        self.study_lock = threading.Lock()  # 线程锁
        self.status_lock = threading.Lock()
        self.active_courses = set()  # 当前正在学习的课程ID集合
        self.active_videos = {}
        self.run_mode = 'normal'

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(f'User_{self.username}')

    def update_status(self, status: str):
        self.current_status = status
        self.logger.info(f"状态更新: {status}")

    def _set_video_active(self, node_id, node_name, active: bool):
        """记录并行节点，避免多个线程互相覆盖当前视频。"""
        with self.status_lock:
            if active:
                self.active_videos[str(node_id)] = node_name
            else:
                self.active_videos.pop(str(node_id), None)
            self.current_video = '、'.join(self.active_videos.values()) or None

    def login(self) -> bool:
        """登录系统"""
        try:
            self.update_status("正在登录")
            
            # 登录请求
            login_data = {
                "platform": "Android",
                "username": self.username,
                "password": self.password,
                "pushId": "140fe1da9e67b9c14a7",
                "school_id": str(self.school_id),
                "imgSign": "533560501d19cc30271a850810b09e3e",
                "imgCode": "cryd"
            }
            
            # 先获取验证码
            try:
                code_url = f"{self.base_url}/service/code/aa"
                self.logger.info(f"获取验证码: {code_url}")
                code_response = self.session.get(
                    code_url,
                    params={"t": int(time.time() * 1000)}
                )
                
                if code_response.status_code != 200:
                    self.logger.error(f"获取验证码失败，状态码: {code_response.status_code}")
                    return False
                
                # 使用 ddddocr 识别验证码
                ocr = create_ocr()
                code = ocr.classification(code_response.content)
                self.logger.info(f"登录验证码识别成功: {code}")
                
                # 添加验证码到登录数据
                login_data["imgCode"] = code
            except Exception as e:
                self.logger.warning(f"获取登录验证码失败: {str(e)}")
            
            # 发送登录请求
            login_url = f"{self.base_url}/api/login.json"
            self.logger.info(f"发送登录请求: {login_url}")
            
            response = self.session.post(
                login_url,
                data=login_data,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Mobile Safari/537.36',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json, text/plain, */*',
                    'Origin': self.base_url,
                    'Referer': f"{self.base_url}/user/login"
                }
            )
            
            # 打印响应内容以便调试
            self.logger.info(f"登录响应状态码: {response.status_code}")
            self.logger.info(f"登录响应: {response.text}")
            
            if response.status_code != 200:
                self.update_status(f"登录失败: HTTP {response.status_code}")
                return False
            
            resp_data = response.json()
            
            if resp_data.get('_code') != 0:
                error_msg = resp_data.get('msg', '未知错误')
                self.update_status(f"登录失败: {error_msg}")
                if resp_data.get('need_code'):
                    self.logger.info("需要验证码，重试登录")
                    return self.login()  # 递归重试
                return False
            
            # 保存token
            self.token = resp_data['result']['data']['token']
            # 更新请求头，确保token格式正确
            self.session.headers.update({
                'token': self.token,
                'Cookie': f'token={self.token}',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Mobile Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json, text/plain, */*',
                'Origin': self.base_url,
                'Referer': f"{self.base_url}/user/login"
            })
            
            # 保存cookies
            for cookie in response.cookies:
                self.session.cookies.set(cookie.name, cookie.value)
            
            self.update_status("登录成功")
            return True
            
        except Exception as e:
            self.logger.error(f"登录失败: {str(e)}")
            self.update_status("登录过程出错")
            return False

    def get_courses(self) -> List[Dict]:
        """获取课程列表"""
        try:
            self.update_status("正在获取课程列表")
            
            # 确保token存在
            if not self.token:
                self.logger.error("Token不存在，需要重新登录")
                return []
            
            # 添加token到请求数据
            course_data = {
                "token": self.token,
                "school_id": str(self.school_id)
            }
            
            self.logger.info(f"获取课程列表，token: {self.token}")
            response = self.session.post(
                f"{self.base_url}/api/course.json",
                data=course_data,
                headers={
                    'token': self.token,
                    'Cookie': f'token={self.token}'
                }
            )
            
            self.logger.info(f"课程列表响应状态码: {response.status_code}")
            self.logger.info(f"课程列表响应: {response.text}")
            
            if response.status_code != 200:
                self.update_status(f"获取课程列表失败: HTTP {response.status_code}")
                return []
            
            resp_data = response.json()
            
            if resp_data.get('_code') != 0:
                error_msg = resp_data.get('msg', '未知错误')
                self.update_status(f"获取课程列表失败: {error_msg}")
                if "登录超时" in error_msg:
                    self.token = None  # 清除token，触发重新登录
                return []
            
            courses = resp_data['result']['list']
            # 只返回未完成且未结束的课程
            incomplete_courses = [
                course for course in courses 
                if course.get('progress', 1) < 1 and course.get('state', 2) != 2
            ]
            
            self.update_status(f"找到 {len(incomplete_courses)} 门未完成课程")
            return incomplete_courses
            
        except Exception as e:
            self.logger.error(f"获取课程列表失败: {str(e)}")
            return []

    def get_chapters(self, course_id: int) -> List[Dict]:
        """获取课程章节"""
        try:
            if not self.token:
                self.logger.error("Token不存在，需要重新登录")
                return []
            
            chapter_data = {
                "token": self.token,
                "courseId": str(course_id),
                "school_id": str(self.school_id)
            }
            
            response = self.session.post(
                f"{self.base_url}/api/course/chapter.json",
                data=chapter_data,
                headers={
                    'token': self.token,
                    'Cookie': f'token={self.token}'
                }
            )
            
            if response.status_code != 200:
                self.logger.error(f"获取章节失败: HTTP {response.status_code}")
                return []
            
            resp_data = response.json()
            
            if resp_data.get('_code') != 0:
                error_msg = resp_data.get('msg', '未知错误')
                self.logger.error(f"获取章节失败: {error_msg}")
                if "登录超时" in error_msg:
                    self.token = None  # 清除token，触发重新登录
                return []
            
            return resp_data['result']['list']
            
        except Exception as e:
            self.logger.error(f"获取章节失败: {str(e)}")
            return []

    def get_node_progress(self, node_id: int, max_retries: int = 3) -> Dict:
        """获取视频节点进度，添加重试机制"""
        for retry in range(max_retries):
            try:
                if not self.token:
                    self.logger.error("Token不存在，需要重新登录")
                    return {}
                
                progress_data = {
                    "token": self.token,
                    "nodeId": str(node_id),
                    "school_id": str(self.school_id)
                }
                
                response = self.session.post(
                    f"{self.base_url}/api/node/video.json",
                    data=progress_data,
                    headers={
                        'token': self.token,
                        'Cookie': f'token={self.token}'
                    },
                    timeout=30  # 添加超时设置
                )
                
                if response.status_code == 502:
                    self.logger.warning(f"获取进度遇到502错误，第{retry + 1}次重试")
                    time.sleep(5)  # 等待5秒后重试
                    continue
                    
                if response.status_code != 200:
                    self.logger.error(f"获取进度失败: HTTP {response.status_code}")
                    if retry < max_retries - 1:
                        time.sleep(5)
                        continue
                    return {}
                
                resp_data = response.json()
                
                if resp_data.get('_code') != 0:
                    error_msg = resp_data.get('msg', '未知错误')
                    self.logger.error(f"获取进度失败: {error_msg}")
                    if "登录超时" in error_msg:
                        self.token = None  # 清除token，触发重新登录
                    if retry < max_retries - 1:
                        time.sleep(5)
                        continue
                    return {}
                
                return resp_data['result']['data']
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"获取进度请求异常: {str(e)}")
                if retry < max_retries - 1:
                    time.sleep(5)
                    continue
                return {}
            except Exception as e:
                self.logger.error(f"获取进度失败: {str(e)}")
                if retry < max_retries - 1:
                    time.sleep(5)
                    continue
                return {}
        
        return {}

    def check_node_status(self, node: Dict) -> str:
        """检查视频节点状态
        返回: "completed" - 已完成, "unlocked" - 已解锁未完成, "locked" - 未解锁, "error" - 错误
        """
        try:
            node_id = node.get('id')
            if not node_id:
                return "error"
            
            progress_data = self.get_node_progress(node_id)
            if not progress_data:
                return "error"
            
            study_total = progress_data.get('study_total', {})
            if study_total:
                state = str(study_total.get('state', ''))
                if state == "2":
                    return "completed"
                if state == "1":
                    return "unlocked"
                if state == "0":
                    return "locked"
                return "error"

            if str(node.get('videoState', '')) == '2':
                return "completed"

            # 未学习过的节点返回空 study_total，不代表被前置节点锁定。
            # 课程明确标记 nodeLock=0 时，所有子节点都可以立即并行。
            if node.get('nodeLock') in (0, '0', False):
                return "unlocked"
            return "error"
                
        except Exception as e:
            self.logger.error(f"检查视频状态失败: {str(e)}")
            return "error"

    def study_node(self, node: Dict) -> bool:
        """学习视频节点，完全匹配Go版本的实现"""
        if not self.running:
            return False
        start_study = True
        while start_study and self.running:
            try:
                node_id = node.get('id')
                if not node_id:
                    self.logger.error(f"节点数据无效: {node}")
                    return False
                    
                node_name = node.get('name', '未知视频')
                self.current_video = node_name
                self.update_status(f"正在学习: {node_name}")
                
                # 获取当前进度
                progress_data = self.get_node_progress(node_id)
                if not progress_data:
                    self.logger.error(f"无法获取视频进度: {node_name}")
                    return False
                
                # 检查视频状态
                study_total = progress_data.get('study_total', {})
                # 如果study_total是列表，说明是初始状态
                if isinstance(study_total, list):
                    study_total = {
                        'duration': '0',
                        'progress': '0.00',
                        'state': '0'
                    }
                    self.logger.info(f"视频初始状态，设置默认进度: {study_total}")
                
                if not study_total:
                    self.logger.error(f"视频数据无效: {progress_data}")
                    return False
                    
                # 如果已经完成，直接返回
                if str(study_total.get('state', '')) == "2":
                    self.update_status(f"视频已完成: {node_name}")
                    return True
                
                # 移除未解锁检查，尝试学习所有视频
                study_time = 1
                study_id = 0
                node_progress = progress_data
                flag = True
                
                # 启动进度监控协程
                def monitor_progress():
                    nonlocal node_progress, flag
                    while flag and self.running:
                        try:
                            progress = self.get_node_progress(node_id)
                            if not progress:
                                self.logger.error(f"获取进度失败: {node_name}")
                                flag = False
                                break
                                
                            # 处理study_total为列表的情况
                            study_total = progress.get('study_total', {})
                            if isinstance(study_total, list):
                                study_total = {
                                    'duration': '0',
                                    'progress': '0.00',
                                    'state': '0'
                                }
                                progress['study_total'] = study_total
                                
                            if str(study_total.get('state', '')) == "2":
                                node['video_state'] = 2
                                break
                            node_progress = progress
                            self._interruptible_sleep(10)
                        except Exception as e:
                            self.logger.error(f"监控进度异常: {str(e)}")
                            flag = False
                            break
                
                # 启动监控线程
                monitor_thread = threading.Thread(target=monitor_progress)
                monitor_thread.daemon = True
                monitor_thread.start()
                
                while node.get('video_state') != 2 and self.running:
                    if not flag:
                        # 使用goto startStudy的逻辑
                        start_study = True
                        break
                    
                    # 发送学习请求
                    study_data = {
                        "token": self.token,
                        "nodeId": str(node_id),
                        "studyTime": str(study_time),
                        "studyId": str(study_id),
                        "school_id": str(self.school_id)
                    }
                    
                    try:
                        self.logger.info(f"准备发送学习请求: studyTime={study_time}, studyId={study_id}")
                        response = self.session.post(
                            f"{self.base_url}/api/node/study.json",
                            data=study_data,
                            headers={
                                'token': self.token,
                                'Cookie': f'token={self.token}'
                            }
                        )
                        
                        self.logger.info(f"学习请求响应状态码: {response.status_code}")
                        self.logger.info(f"学习请求响应内容: {response.text}")
                        
                        if response.status_code != 200:
                            self.logger.error(f"学习请求失败: HTTP {response.status_code}")
                            time.sleep(5)
                            continue
                        
                        try:
                            resp_data = response.json()
                        except json.JSONDecodeError as e:
                            self.logger.error(f"解析响应JSON失败: {str(e)}, 响应内容: {response.text}")
                            time.sleep(5)
                            continue
                            
                        self.logger.info(f"学习请求响应数据: {resp_data}")
                        
                        if resp_data.get('_code') != 0:
                            error_msg = resp_data.get('msg', '未知错误')
                            if resp_data.get('need_code'):
                                # 处理验证码
                                self.logger.info("需要验证码，开始处理")
                                code = self.handle_captcha()
                                study_data['code'] = code + "_"
                                self.logger.info(f"验证码处理完成: {code}")
                                continue
                            # 并行任务遇到前置限制时结束该节点，交由课程调度器处理。
                            if "未解锁" in error_msg or "未开始" in error_msg:
                                self.logger.warning(f"视频尚未解锁，等待前置节点: {error_msg}")
                                flag = False
                                monitor_thread.join(timeout=1)
                                return False
                            self.logger.error(f"学习请求失败: {error_msg}")
                            if "登录超时" in error_msg:
                                self.token = None  # 清除token，触发重新登录
                                return False
                            time.sleep(5)
                            continue
                        
                        # 验证学习请求是否成功
                        study_result = resp_data.get('result', {}).get('data', {})
                        if not study_result:
                            self.logger.error(f"学习请求响应中result.data为空: {resp_data}")
                            time.sleep(5)
                            continue
                            
                        if 'studyId' not in study_result:
                            self.logger.error(f"学习请求响应中缺少studyId: {study_result}")
                            time.sleep(5)
                            continue
                        
                        study_id = study_result['studyId']
                        self.logger.info(f"成功获取studyId: {study_id}")
                        
                        # 获取当前进度
                        study_total = node_progress.get('study_total', {})
                        if isinstance(study_total, list):
                            study_total = {
                                'duration': '0',
                                'progress': '0.00',
                                'state': '0'
                            }
                            node_progress['study_total'] = study_total
                            
                        progress = study_total.get('progress', '0.00')
                        if not progress:
                            progress = '0.00'
                            self.logger.warning(f"进度为空，使用默认值: {progress}")
                        
                        try:
                            progress_float = float(progress)
                            self.logger.info(f"{node_name}[nodeId={node_id}], 学习成功[studyId={study_id}], 当前进度: {progress_float*100:.0f}%")
                        except ValueError as e:
                            self.logger.error(f"解析进度失败: {progress}, 错误: {str(e)}")
                            time.sleep(5)
                            continue
                        
                        self.logger.info(f"准备增加学习时间: {study_time} -> {study_time + 10}")
                        study_time += 10
                        self.logger.info(f"等待10秒后继续学习")
                        if not self._interruptible_sleep(10):
                            break
                        
                    except requests.exceptions.RequestException as e:
                        self.logger.error(f"学习请求网络异常: {str(e)}")
                        time.sleep(5)
                        continue
                    except Exception as e:
                        self.logger.error(f"学习请求异常: {str(e)}")
                        time.sleep(5)
                        continue
                
                # 如果正常完成，退出循环
                if node.get('video_state') == 2:
                    start_study = False
                
            except Exception as e:
                self.logger.error(f"学习视频失败: {str(e)}")
                return False
        
        # 停止监控线程
        flag = False
        monitor_thread.join(timeout=1)

        if not self.running:
            return False
        
        self.update_status(f"视频已完成: {node_name}")
        return True

    def handle_captcha(self) -> str:
        """处理验证码"""
        try:
            self.update_status("正在识别验证码")
            
            # 获取验证码图片
            response = self.session.get(
                f"{self.base_url}/service/code/aa",
                params={"t": int(time.time() * 1000)}
            )
            
            # 使用 ddddocr 识别验证码
            ocr = create_ocr()
            code = ocr.classification(response.content)
            
            self.update_status(f"验证码识别成功: {code}")
            return code
            
        except Exception as e:
            self.logger.error(f"验证码识别失败: {str(e)}")
            return ""

    def _get_video_nodes(self, chapters: List[Dict]) -> List[Dict]:
        """按课程原始顺序展开视频节点，并兼容嵌套子节点。"""
        nodes = []
        seen = set()

        def collect(items):
            for node in items or []:
                if not isinstance(node, dict):
                    continue
                node_id = node.get('id')
                if node.get('tabVideo') and node_id is not None and node_id not in seen:
                    seen.add(node_id)
                    nodes.append(node)
                for key in ('nodeList', 'children', 'childList'):
                    children = node.get(key)
                    if isinstance(children, list):
                        collect(children)

        for chapter in chapters:
            self.logger.info(f"当前第 {chapter.get('idx', '?')} 章: {chapter.get('name', '未知章节')}")
            collect(chapter.get('nodeList', []))
        return nodes

    def _study_node_tracked(self, node: Dict) -> bool:
        node_id = node.get('id')
        node_name = node.get('name', '未知视频')
        self._set_video_active(node_id, node_name, True)
        try:
            return self.study_node(node)
        finally:
            self._set_video_active(node_id, node_name, False)

    def _study_node_batch(self, nodes: List[Dict], node_limit: int) -> bool:
        """并行一批节点；同一批内没有前后依赖。"""
        if not nodes:
            return True
        results = []
        workers = min(node_limit, len(nodes))
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix=f'{self.username}_nodes'
        ) as executor:
            futures = {
                executor.submit(self._study_node_tracked, node): node
                for node in nodes
            }
            for future in concurrent.futures.as_completed(futures):
                node = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    self.logger.error(f"处理视频节点失败[{node.get('name')}]: {str(e)}")
                    results.append(False)
        return self.running and all(results)

    def _get_node_statuses(self, nodes: List[Dict], node_limit: int) -> List[str]:
        workers = min(node_limit, len(nodes))
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix=f'{self.username}_status'
        ) as executor:
            return list(executor.map(self.check_node_status, nodes))

    def _study_nodes_auto(self, nodes: List[Dict], node_limit: int) -> bool:
        """并行已解锁前缀，锁定节点必须等待前面的批次完成。"""
        pending = list(nodes)
        locked_wait_rounds = 0

        while pending and self.running:
            statuses = self._get_node_statuses(pending, node_limit)
            ready = []
            remaining = []
            blocked = False

            for node, status in zip(pending, statuses):
                if status == 'completed':
                    continue
                if status == 'unlocked' and not blocked:
                    ready.append(node)
                else:
                    # 第一个锁定或未知状态之后的节点不能提前并行。
                    blocked = True
                    remaining.append(node)

            if ready:
                locked_wait_rounds = 0
                self.update_status(f"同时学习 {len(ready)} 个已解锁节点")
                self.logger.info(f"并行已解锁节点: {[node.get('name') for node in ready]}")
                if not self._study_node_batch(ready, node_limit):
                    return False
                pending = remaining
                continue

            if not remaining:
                return True

            first_status = self.check_node_status(remaining[0])
            if first_status == 'error':
                # 无法确认前置状态时保守降级，不直接并发后续节点。
                self.logger.warning(f"无法确认节点状态，转为顺序处理: {remaining[0].get('name')}")
                if not self._study_node_tracked(remaining[0]):
                    return False
                pending = remaining[1:]
                locked_wait_rounds = 0
                continue

            locked_wait_rounds += 1
            if locked_wait_rounds > 3:
                self.logger.error(f"前置节点尚未完成，暂停本课程: {remaining[0].get('name')}")
                return False
            self.update_status(f"等待前置节点解锁: {remaining[0].get('name')}")
            if not self._interruptible_sleep(5):
                return False

        return self.running

    def study_course(
        self,
        course: Dict,
        parallel_nodes: bool = False,
        node_mode: str = 'auto',
        node_limit: int = 3
    ) -> bool:
        """学习整个课程，可按课程选择自动前置、全部并行或严格顺序。"""
        try:
            course_name = course.get('name', '未知课程')
            course_id = course.get('id')
            if not course_id:
                self.logger.error(f"课程数据无效: {course}")
                return False

            self.current_course = course_name
            self.update_status(f"开始学习课程: {course_name}")
            chapters = self.get_chapters(course_id)
            if not chapters:
                return False

            nodes = self._get_video_nodes(chapters)
            if not nodes:
                self.logger.info(f"课程没有视频节点: {course_name}")
                return True

            if parallel_nodes and node_mode != 'sequential':
                try:
                    node_limit = max(1, min(20, int(node_limit)))
                except (TypeError, ValueError):
                    node_limit = 3

                if node_mode == 'parallel':
                    self.update_status(f"{course_name}: 全部节点并行 ({len(nodes)} 个)")
                    return self._study_node_batch(nodes, node_limit)

                self.update_status(f"{course_name}: 自动识别前置节点")
                return self._study_nodes_auto(nodes, node_limit)

            # 普通启动及“严格顺序”模式仍按课程原始顺序处理。
            for node in nodes:
                if not self.running:
                    return False
                try:
                    if parallel_nodes:
                        success = self._study_node_tracked(node)
                        if not success:
                            return False
                    else:
                        self.study_node(node)
                except Exception as e:
                    self.logger.error(f"处理视频节点失败: {str(e)}")
                    if parallel_nodes:
                        return False

            return True

        except Exception as e:
            self.logger.error(f"学习课程失败: {str(e)}")
            return False

    def study_course_thread(self, course: Dict):
        """在线程中学习课程"""
        try:
            course_id = course.get('id')
            if not course_id:
                return
            
            with self.study_lock:
                if course_id in self.active_courses:
                    return
                self.active_courses.add(course_id)
            
            try:
                self.study_course(course)
            finally:
                with self.study_lock:
                    self.active_courses.remove(course_id)
        except Exception as e:
            self.logger.error(f"课程学习线程异常: {str(e)}")

    def _interruptible_sleep(self, seconds: float) -> bool:
        """可中断的睡眠：每秒检查一次 self.running，被 stop 时立刻返回。
        返回 True = 睡眠完整结束；False = 被 stop 打断。
        """
        end_time = time.time() + seconds
        while self.running and time.time() < end_time:
            time.sleep(min(1.0, max(0.05, end_time - time.time())))
        return self.running

    def run(
        self,
        parallel_nodes: bool = False,
        course_ids: Optional[List[str]] = None,
        course_modes: Optional[Dict[str, str]] = None,
        node_limit: int = 3,
        course_limit: Optional[int] = None
    ):
        """主运行逻辑；并行模式可限定课程，并为每门课指定节点策略。"""
        self.running = True
        self.run_mode = 'parallel' if parallel_nodes else 'normal'
        self.update_status("开始运行")

        if course_limit is not None:
            try:
                self.study_limit = max(1, min(10, int(course_limit)))
            except (TypeError, ValueError):
                pass
        selected_ids = {str(course_id) for course_id in course_ids} if course_ids else None
        course_modes = course_modes or {}
        
        while self.running:
            try:
                # 登录
                if not self.login():
                    self.update_status("登录失败，等待重试")
                    if not self._interruptible_sleep(60):
                        break
                    continue
                
                # 获取未完成课程
                courses = self.get_courses()
                if selected_ids is not None:
                    courses = [
                        course for course in courses
                        if str(course.get('id')) in selected_ids
                    ]
                if not courses:
                    self.update_status("所选课程均已完成或不可用，等待重试" if selected_ids is not None else "没有未完成课程，等待重试")
                    if not self._interruptible_sleep(300):
                        break
                    continue
                
                # 使用线程池处理课程
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.study_limit) as executor:
                    # 提交所有课程到线程池
                    futures = []
                    for course in courses:
                        if not self.running:
                            break
                            
                        # 检查课程状态
                        if course.get('state') == 2:
                            self.logger.info(f"当前课程[{course.get('name')}][{course.get('id')}] 已结束, 跳过")
                            continue
                            
                        if course.get('progress', 1) >= 1:
                            self.logger.info(f"当前课程[{course.get('name')}][{course.get('id')}] 进度: {course.get('progress1', '未知')}, 跳过")
                            continue
                            
                        self.logger.info(f"当前课程[{course.get('name')}][{course.get('id')}] 进度: {course.get('progress1', '未知')}")
                        node_mode = course_modes.get(str(course.get('id')), 'auto')
                        futures.append(executor.submit(
                            self.study_course,
                            course,
                            parallel_nodes=parallel_nodes,
                            node_mode=node_mode,
                            node_limit=node_limit
                        ))
                    
                    # 等待所有课程完成（可被 stop 打断）
                    for future in concurrent.futures.as_completed(futures):
                        if not self.running:
                            # 不再等待后续 future，立即退出
                            break
                        try:
                            future.result()
                        except Exception as e:
                            self.logger.error(f"课程学习异常: {str(e)}")
                
                # 如果被 stop，不再进入下一轮等待
                if not self.running:
                    break
                
                # 完成一轮后等待
                wait_time = random.randint(300, 600)
                self.update_status(f"本轮完成，等待 {wait_time} 秒")
                if not self._interruptible_sleep(wait_time):
                    break
                
            except Exception as e:
                self.logger.error(f"运行出错: {str(e)}")
                self.update_status("运行过程出错")
                if not self._interruptible_sleep(60):
                    break
        
        # 退出循环后重置状态
        self.current_status = "已停止"
        self.current_course = None
        self.current_video = None
        with self.status_lock:
            self.active_videos.clear()

    def stop(self):
        """停止运行"""
        self.running = False
        self.update_status("正在停止")
        # 等待所有学习线程结束
        for thread in self.study_threads:
            if thread.is_alive():
                thread.join(timeout=2)
        # 状态在 run() 退出后会被设为"已停止"，这里不重复设置
        # 避免 run() 还未退出时状态被覆盖回"已停止"造成不一致

    def get_status(self) -> Dict:
        """获取当前状态"""
        with self.status_lock:
            active_nodes = len(self.active_videos)
            current_video = '、'.join(self.active_videos.values()) or self.current_video
        return {
            'status': self.current_status,
            'course': self.current_course,
            'video': current_video,
            'running': self.running,
            'mode': self.run_mode,
            'active_nodes': active_nodes
        }
