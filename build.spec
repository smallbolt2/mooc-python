# -*- mode: python ; coding: utf-8 -*-

# 1. 配置分析步骤
a = Analysis(
    ['app.py'],                     # 你的主程序入口
    pathex=[],                      # 额外的模块搜索路径
    binaries=[],                    # 需要打包的二进制文件（如.dll/.so）
    datas=[                         # 需要打包的资源文件
        ('config.json', '.'),       # 单个配置文件
        ('templates', 'templates'), # 整个 templates 文件夹
        ('static', 'static'),       # 整个 static 文件夹
        ('mooc', 'mooc'),           # 整个 mooc 文件夹
    ],
    hiddenimports=[
        'gevent',
        'gevent.monkey',
        'gevent.websocket',
        'engineio.async_drivers.gevent',
        'engineio.async_drivers.gevent_uwsgi',
        'engineio.async_drivers.threading',
        'socketio',
        'engineio',
        'simple_websocket'  # 一些版本的gevent-websocket可能依赖它
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# 2. 创建 PYZ 存档（将纯 Python 模块打包）
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 3. 生成可执行文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='smallbolt',              # 生成的 exe 文件名
    debug=False,
    strip=False,
    upx=True,
    console=True,                  # 保持为 True 便于调试
    icon='icon.ico',               # 你的程序图标
)