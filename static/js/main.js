$(document).ready(function() {
    let autoScroll = true;
    let lastLogCount = 0;
    let parallelUsername = '';
    let parallelUserKey = '';
    let parallelLoadToken = 0;
    let parallelCoursesLoaded = false;
    const socket = io();

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>'"]/g, function(char) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[char];
        });
    }

    function userIdentity(user) {
        return String(user.user_key || user.username || '');
    }

    function findUserItem(userKey) {
        return $('.user-item').filter(function() {
            return $(this).attr('data-user-key') === userKey;
        });
    }
    
    // WebSocket连接处理
    socket.on('connect', function() {
        console.log('WebSocket connected');
    });
    
    socket.on('disconnect', function() {
        console.log('WebSocket disconnected');
    });
    
    // 处理实时日志
    socket.on('log_message', function(data) {
        const logEntry = createLogEntry(data);
        $('#log').append(logEntry);
        
        if (autoScroll) {
            $('#log').scrollTop($('#log')[0].scrollHeight);
        }
        
        lastLogCount++;
    });
    
    // 创建日志条目
    function createLogEntry(log) {
        const levelClass = log.level === 'ERROR' ? 'error' : 
                          log.level === 'INFO' ? 'info' : 
                          log.level === 'WARNING' ? 'warning' : 'secondary';
        
        const levelIcon = log.level === 'ERROR' ? 'fa-exclamation-circle' : 
                         log.level === 'INFO' ? 'fa-info-circle' : 
                         log.level === 'WARNING' ? 'fa-exclamation-triangle' : 'fa-circle';
        
        return `
            <div class="log-entry ${levelClass}">
                <div class="d-flex align-items-start">
                    <i class="fas ${levelIcon} me-2 mt-1"></i>
                    <div class="flex-grow-1">
                        <div class="timestamp">[${log.timestamp}]</div>
                        <div class="message">${log.message}</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    // 标签页切换
    $('.menu-item').click(function() {
        const tabId = $(this).data('tab');
        
        // 更新菜单项状态
        $('.menu-item').removeClass('active');
        $(this).addClass('active');
        
        // 更新标签页内容
        $('.tab-content').removeClass('active');
        $('#' + tabId).addClass('active');
    });
    
    // 更新当前时间
    function updateCurrentTime() {
        const now = new Date();
        const timeString = now.toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        $('#currentTime').text(timeString);
    }
    
    // 定期更新系统状态
    function updateStatus() {
        $.get('/api/status', function(data) {
            const runningUsers = data.running_users || 0;
            const totalUsers = data.total_users || 0;
            
            const statusClass = runningUsers > 0 ? 'success' : 'info';
            const statusIcon = runningUsers > 0 ? 'fa-check-circle' : 'fa-info-circle';
            const statusText = runningUsers > 0 ? `运行中 (${runningUsers}/${totalUsers})` : '已停止';
            
            $('#status').html(`
                <div class="status-display">
                    <i class="fas ${statusIcon}" style="color: ${statusClass === 'success' ? '#10b981' : '#3b82f6'}"></i>
                    <span>${statusText}</span>
                </div>
            `);
            
            // 更新系统状态
            $('#systemStatus').text(runningUsers > 0 ? '运行中' : '已停止');
            
        }).fail(function() {
            $('#status').html(`
                <div class="status-display">
                    <i class="fas fa-exclamation-triangle" style="color: #ef4444"></i>
                    <span>连接失败</span>
                </div>
            `);
        });
    }

    // 定期更新用户列表
    // 缓存上次渲染的 HTML，避免频繁重建 DOM 导致 click 事件失效
    let lastUserListHtml = '';
    function updateUserList(force) {
        $.get('/api/users', function(data) {
            let html = '';
            let totalUsers = 0;
            let runningUsers = 0;
            let totalCourses = 0;
            let totalVideos = 0;
            
            data.forEach(function(user) {
                totalUsers++;
                const userKey = userIdentity(user);
                const username = escapeHtml(user.username);
                const site = escapeHtml(user.site || '');
                const keyAttribute = escapeHtml(userKey);
                const siteAttribute = escapeHtml(user.site || '');
                
                const statusClass = user.status && user.status.includes('失败') ? 'danger' : 
                                  user.status && user.status.includes('成功') ? 'success' : 
                                  user.status && user.status.includes('等待') ? 'warning' : 'info';
                
                const statusIcon = user.status && user.status.includes('失败') ? 'fa-exclamation-circle' : 
                                 user.status && user.status.includes('成功') ? 'fa-check-circle' : 
                                 user.status && user.status.includes('等待') ? 'fa-clock' : 'fa-info-circle';
                
                html += `
                    <div class="user-item" data-user-key="${keyAttribute}" data-username="${username}">
                        <div class="user-header">
                            <div class="user-name">
                                <i class="fas fa-user me-2" style="color: #3b82f6"></i>
                                ${username}
                                ${site ? `<small class="user-site">${site}</small>` : ''}
                            </div>
                            <div class="user-controls">
                                <button class="btn-start-user btn-sm btn-success me-1" data-user-key="${keyAttribute}" data-username="${username}" title="启动该账号">
                                    <i class="fas fa-play"></i> 启动
                                </button>
                                <button class="btn-stop-user btn-sm btn-danger me-1" data-user-key="${keyAttribute}" data-username="${username}" title="停止该账号">
                                    <i class="fas fa-stop"></i> 停止
                                </button>
                                <button class="btn-parallel-user btn-node-parallel btn-sm me-1" data-user-key="${keyAttribute}" data-username="${username}" data-site="${siteAttribute}" title="选择课程并同时刷节点">
                                    <i class="fas fa-layer-group"></i> 并行节点
                                </button>
                                <button class="btn-edit-user btn-sm btn-warning me-1" data-user-key="${keyAttribute}" data-username="${username}" title="编辑账号">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="btn-delete-user btn-sm btn-secondary" data-user-key="${keyAttribute}" data-username="${username}" title="删除账号">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                        <div class="user-details">
                            <div class="user-detail">
                                <i class="fas fa-info-circle" style="color: #3b82f6"></i>
                                <span>状态: 未启动</span>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            if (data.length === 0) {
                html = `
                    <div class="loading-placeholder">
                        <i class="fas fa-users fa-3x mb-3" style="color: #cbd5e1"></i>
                        <p>暂无用户数据</p>
                        <small>请检查配置文件</small>
                    </div>
                `;
            }
            
            // 关键修复：只有 HTML 真的变化时才重建 DOM，避免点击中的元素被意外销毁
            if (force || html !== lastUserListHtml) {
                $('#userList').html(html);
                lastUserListHtml = html;
                updateRunningUsers();
            }
            $('#userCount').text(totalUsers);
            
            // 更新统计信息
            $('#totalUsers').text(totalUsers);
            $('#runningUsers').text(runningUsers);
            $('#totalCourses').text(totalCourses);
            $('#totalVideos').text(totalVideos);
            
            // 添加数字动画效果
            animateNumbers();
        }).fail(function() {
            $('#userList').html(`
                <div class="loading-placeholder">
                    <i class="fas fa-exclamation-triangle fa-3x mb-3" style="color: #ef4444"></i>
                    <p>加载用户数据失败</p>
                    <small>请检查网络连接</small>
                </div>
            `);
        });
    }

    // 定期更新运行中的用户状态
    // 缓存每个用户上次的状态 HTML，避免频繁重建子 DOM
    const userStatusCache = {};
    function updateRunningUsers() {
        $.get('/api/status', function(data) {
            const runningUserKeys = new Set((data.users || []).map(userIdentity));
            
            // 1. 处理未运行的用户：恢复为「未启动」状态
            $('.user-item').each(function() {
                const $item = $(this);
                const userKey = $item.attr('data-user-key');
                if (!userKey) return;
                
                if (!runningUserKeys.has(userKey)) {
                    const defaultHtml = `
                        <div class="user-detail">
                            <i class="fas fa-info-circle" style="color: #3b82f6"></i>
                            <span>状态: 未启动</span>
                        </div>
                    `;
                    if (userStatusCache[userKey] !== defaultHtml) {
                        $item.find('.user-details').html(defaultHtml);
                        userStatusCache[userKey] = defaultHtml;
                    }
                    // 未运行的用户：启动可点、停止不可点
                    $item.find('.btn-start-user').prop('disabled', false).removeClass('disabled');
                    $item.find('.btn-stop-user').prop('disabled', true).addClass('disabled');
                    $item.find('.btn-parallel-user').prop('disabled', false).removeClass('disabled');
                }
            });
            
            // 2. 更新正在运行/已启动的用户
            (data.users || []).forEach(function(user) {
                const userKey = userIdentity(user);
                const userItem = findUserItem(userKey);
                if (userItem.length === 0) return;
                
                const statusClass = user.status && user.status.includes('失败') ? 'danger' : 
                                  user.status && user.status.includes('成功') ? 'success' : 
                                  user.status && user.status.includes('等待') ? 'warning' : 'info';
                
                const statusIcon = user.status && user.status.includes('失败') ? 'fa-exclamation-circle' : 
                                 user.status && user.status.includes('成功') ? 'fa-check-circle' : 
                                 user.status && user.status.includes('等待') ? 'fa-clock' : 'fa-info-circle';
                
                const newHtml = `
                    <div class="user-detail">
                        <i class="fas ${statusIcon}" style="color: ${statusClass === 'success' ? '#10b981' : statusClass === 'danger' ? '#ef4444' : statusClass === 'warning' ? '#f59e0b' : '#3b82f6'}"></i>
                        <span>状态: ${user.status || '未知'}</span>
                    </div>
                    ${user.course ? `
                        <div class="user-detail">
                            <i class="fas fa-book" style="color: #f59e0b"></i>
                            <span>当前课程: ${user.course}</span>
                        </div>
                    ` : ''}
                    ${user.video ? `
                        <div class="user-detail">
                            <i class="fas fa-video" style="color: #8b5cf6"></i>
                            <span>当前视频: ${user.video}</span>
                        </div>
                    ` : ''}
                `;
                
                // 只在 HTML 变化时才重建子 DOM
                if (userStatusCache[userKey] !== newHtml) {
                    userItem.find('.user-details').html(newHtml);
                    userStatusCache[userKey] = newHtml;
                }
                
                // 按钮状态每次都更新（不重建 DOM，只改 disabled 属性）
                const startBtn = userItem.find('.btn-start-user');
                const stopBtn = userItem.find('.btn-stop-user');
                const parallelBtn = userItem.find('.btn-parallel-user');
                
                if (user.running) {
                    startBtn.prop('disabled', true).addClass('disabled');
                    stopBtn.prop('disabled', false).removeClass('disabled');
                    parallelBtn.prop('disabled', true).addClass('disabled');
                } else {
                    startBtn.prop('disabled', false).removeClass('disabled');
                    stopBtn.prop('disabled', true).addClass('disabled');
                    parallelBtn.prop('disabled', false).removeClass('disabled');
                }
            });
        });
    }

    // 数字动画效果
    function animateNumbers() {
        $('.stat-number').each(function() {
            const $this = $(this);
            const countTo = parseInt($this.text());
            
            $({ countNum: 0 }).animate({
                countNum: countTo
            }, {
                duration: 1000,
                easing: 'swing',
                step: function() {
                    $this.text(Math.floor(this.countNum));
                },
                complete: function() {
                    $this.text(this.countNum);
                }
            });
        });
    }
    
    // 显示通知
    function showNotification(message, type = 'info') {
        const alertClass = type === 'success' ? 'alert-success' : 
                          type === 'error' ? 'alert-danger' : 
                          type === 'warning' ? 'alert-warning' : 'alert-info';
        
        const icon = type === 'success' ? 'fa-check-circle' : 
                    type === 'error' ? 'fa-exclamation-circle' : 
                    type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle';
        
        const notification = $(`
            <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
                <i class="fas ${icon} me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `);
        
        $('#notificationContainer').append(notification);
        
        // 自动消失
        setTimeout(function() {
            notification.alert('close');
        }, 5000);
    }
    
    // 启动单个用户
    $(document).on('click', '.btn-start-user', function() {
        const username = $(this).attr('data-username');
        const userKey = $(this).attr('data-user-key');
        const btn = $(this);
        
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> 启动中...');
        
        $.ajax({
            url: '/api/start',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ username: username, user_key: userKey }),
            success: function(response) {
                if (response.success) {
                    showNotification(response.message, 'success');
                } else {
                    showNotification(response.message, 'error');
                }
            },
            error: function() {
                showNotification('启动用户失败，请检查网络连接', 'error');
            },
            complete: function() {
                btn.prop('disabled', false).html('<i class="fas fa-play"></i> 启动');
            }
        });
    });
    
    // 停止单个用户
    $(document).on('click', '.btn-stop-user', function() {
        const username = $(this).attr('data-username');
        const userKey = $(this).attr('data-user-key');
        const btn = $(this);
        
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> 停止中...');
        
        $.ajax({
            url: '/api/stop',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ username: username, user_key: userKey }),
            success: function(response) {
                if (response.success) {
                    showNotification(response.message, 'success');
                } else {
                    showNotification(response.message, 'error');
                }
            },
            error: function() {
                showNotification('停止用户失败，请检查网络连接', 'error');
            },
            complete: function() {
                btn.prop('disabled', false).html('<i class="fas fa-stop"></i> 停止');
            }
        });
    });
    
    // 启动全部用户
    $('#startAllBtn').click(function() {
        const btn = $(this);
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> 启动中...');
        
        // 获取所有用户并逐个启动
        $.get('/api/users', function(users) {
            let startedCount = 0;
            let totalUsers = users.length;
            
            if (totalUsers === 0) {
                showNotification('没有找到用户配置', 'warning');
                btn.prop('disabled', false).html('<i class="fas fa-play"></i> 启动全部');
                return;
            }
            
            users.forEach(function(user, index) {
                setTimeout(function() {
                    $.ajax({
                        url: '/api/start',
                        method: 'POST',
                        contentType: 'application/json',
                        data: JSON.stringify({ username: user.username, user_key: userIdentity(user) }),
                        success: function(response) {
                            if (response.success) {
                                startedCount++;
                            }
                            
                            if (index === totalUsers - 1) {
                                showNotification(`成功启动 ${startedCount}/${totalUsers} 个用户`, 'success');
                                btn.prop('disabled', false).html('<i class="fas fa-play"></i> 启动全部');
                            }
                        },
                        error: function() {
                            if (index === totalUsers - 1) {
                                showNotification('启动用户时出现错误', 'error');
                                btn.prop('disabled', false).html('<i class="fas fa-play"></i> 启动全部');
                            }
                        }
                    });
                }, index * 1000); // 每个用户间隔1秒启动
            });
        });
    });
    
    // 停止全部用户
    $('#stopAllBtn').click(function() {
        const btn = $(this);
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> 停止中...');
        
        $.ajax({
            url: '/api/stop_all',
            method: 'POST',
            contentType: 'application/json',
            success: function(response) {
                if (response.success) {
                    showNotification(response.message, 'success');
                } else {
                    showNotification(response.message, 'error');
                }
            },
            error: function() {
                showNotification('停止所有用户失败，请检查网络连接', 'error');
            },
            complete: function() {
                btn.prop('disabled', false).html('<i class="fas fa-stop"></i> 停止全部');
            }
        });
    });

    function updateParallelSelectAll() {
        const $checkboxes = $('.parallel-course-checkbox');
        const allChecked = $checkboxes.length > 0 && $checkboxes.filter(':checked').length === $checkboxes.length;
        $('#parallelSelectAllBtn').text(allChecked ? '取消全选' : '全选');
    }

    function closeParallelModal() {
        parallelLoadToken++;
        parallelCoursesLoaded = false;
        $('#parallelModal').fadeOut(150, function() {
            $(this).attr('aria-hidden', 'true');
        });
    }

    function courseProgressText(course) {
        if (course.progress_text) return String(course.progress_text);
        const progress = Number(course.progress);
        if (!Number.isFinite(progress)) return '';
        const percent = progress <= 1 ? progress * 100 : progress;
        return `已完成 ${Math.round(percent * 10) / 10}%`;
    }

    function renderParallelCourses(courses) {
        if (!courses.length) {
            parallelCoursesLoaded = false;
            $('#parallelCourseList').html('<div class="parallel-placeholder">没有未完成的课程</div>');
            $('#parallelStartBtn').prop('disabled', true);
            $('#parallelSelectAllBtn').prop('disabled', true);
            return;
        }

        const html = courses.map(function(course) {
            const id = escapeHtml(course.id);
            const progress = courseProgressText(course);
            return `
                <div class="parallel-course-row" data-course-id="${id}">
                    <label class="parallel-course-check">
                        <input type="checkbox" class="parallel-course-checkbox" checked>
                        <span class="parallel-course-name">
                            ${escapeHtml(course.name)}
                            ${progress ? `<small class="parallel-course-progress">${escapeHtml(progress)}</small>` : ''}
                        </span>
                    </label>
                    <select class="parallel-course-mode" aria-label="${escapeHtml(course.name)}节点模式">
                        <option value="auto">自动识别前置</option>
                        <option value="parallel">全部节点并行</option>
                        <option value="sequential">按节点顺序</option>
                    </select>
                </div>
            `;
        }).join('');

        parallelCoursesLoaded = true;
        $('#parallelCourseList').html(html);
        $('#parallelStartBtn').prop('disabled', false);
        $('#parallelSelectAllBtn').prop('disabled', false);
        updateParallelSelectAll();
    }

    function loadParallelCourses() {
        const requestToken = ++parallelLoadToken;
        parallelCoursesLoaded = false;
        $('#parallelLoadError').hide();
        $('#parallelCourseList').html(`
            <div class="parallel-placeholder">
                <i class="fas fa-spinner fa-spin"></i> 正在读取课程...
            </div>
        `);
        $('#parallelStartBtn').prop('disabled', true);
        $('#parallelSelectAllBtn').prop('disabled', true);

        $.ajax({
            url: '/api/parallel/courses',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ username: parallelUsername, user_key: parallelUserKey }),
            success: function(response) {
                if (requestToken !== parallelLoadToken) return;
                if (response.success) {
                    renderParallelCourses(response.courses || []);
                    return;
                }
                $('#parallelCourseList').empty();
                $('#parallelLoadError').show().find('span').text(response.message || '读取课程失败');
            },
            error: function(xhr) {
                if (requestToken !== parallelLoadToken) return;
                const message = xhr.responseJSON && xhr.responseJSON.message;
                $('#parallelCourseList').empty();
                $('#parallelLoadError').show().find('span').text(message || '读取课程失败，请检查网络连接');
            }
        });
    }

    $(document).on('click', '.btn-parallel-user', function() {
        parallelUsername = $(this).attr('data-username');
        parallelUserKey = $(this).attr('data-user-key');
        const site = $(this).attr('data-site');
        $('#parallelUsername').text(site ? `${parallelUsername} · ${site}` : parallelUsername);
        $('#parallelNodeLimit').val(3);
        $('#parallelCourseLimit').val(1);
        $('#parallelStartBtn').html('<i class="fas fa-layer-group"></i> 开始并行');
        $('#parallelModal').attr('aria-hidden', 'false').fadeIn(150);
        loadParallelCourses();
    });

    $(document).on('change', '.parallel-course-checkbox', function() {
        const $row = $(this).closest('.parallel-course-row');
        $row.find('.parallel-course-mode').prop('disabled', !this.checked);
        updateParallelSelectAll();
    });

    $('#parallelSelectAllBtn').click(function() {
        const $checkboxes = $('.parallel-course-checkbox');
        const shouldCheck = $checkboxes.filter(':checked').length !== $checkboxes.length;
        $checkboxes.prop('checked', shouldCheck).each(function() {
            $(this).closest('.parallel-course-row').find('.parallel-course-mode').prop('disabled', !shouldCheck);
        });
        updateParallelSelectAll();
    });

    $('#parallelRetryBtn').click(loadParallelCourses);
    $('#parallelCloseBtn, #parallelCancelBtn').click(closeParallelModal);
    $('#parallelModal').click(function(event) {
        if (event.target === this) closeParallelModal();
    });
    $(document).keydown(function(event) {
        if (event.key === 'Escape' && $('#parallelModal').is(':visible')) {
            closeParallelModal();
        }
    });

    $('#parallelForm').submit(function(event) {
        event.preventDefault();
        if (!parallelCoursesLoaded) return;

        const $selectedRows = $('.parallel-course-row').filter(function() {
            return $(this).find('.parallel-course-checkbox').is(':checked');
        });
        if (!$selectedRows.length) {
            showNotification('请至少选择一门课程', 'warning');
            return;
        }

        const courseIds = [];
        const courseModes = {};
        $selectedRows.each(function() {
            const courseId = String($(this).attr('data-course-id'));
            courseIds.push(courseId);
            courseModes[courseId] = $(this).find('.parallel-course-mode').val();
        });

        const btn = $('#parallelStartBtn');
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> 启动中...');
        $.ajax({
            url: '/api/parallel/start',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                username: parallelUsername,
                user_key: parallelUserKey,
                course_ids: courseIds,
                course_modes: courseModes,
                node_limit: parseInt($('#parallelNodeLimit').val(), 10),
                course_limit: parseInt($('#parallelCourseLimit').val(), 10)
            }),
            success: function(response) {
                showNotification(response.message, response.success ? 'success' : 'error');
                if (response.success) {
                    closeParallelModal();
                    updateRunningUsers();
                }
            },
            error: function(xhr) {
                const message = xhr.responseJSON && xhr.responseJSON.message;
                showNotification(message || '启动并行任务失败，请检查网络连接', 'error');
            },
            complete: function() {
                btn.prop('disabled', !parallelCoursesLoaded).html('<i class="fas fa-layer-group"></i> 开始并行');
            }
        });
    });
    
    // 日志控制
    $('#autoScrollBtn').click(function() {
        autoScroll = !autoScroll;
        $(this).toggleClass('active');
        if (autoScroll) {
            $('#log').scrollTop($('#log')[0].scrollHeight);
        }
    });
    
    $('#clearLogBtn').click(function() {
        $('#log').empty();
        lastLogCount = 0;
        showNotification('日志已清除', 'info');
    });
    
    // 初始化
    updateCurrentTime();
    updateStatus();
    updateUserList();
    updateRunningUsers();
    
    // 定时更新
    setInterval(updateCurrentTime, 1000);
    setInterval(updateStatus, 5000);
    setInterval(updateUserList, 10000);
    setInterval(updateRunningUsers, 3000);
}); 
