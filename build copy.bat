@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ====== 路径配置 ======
set "PYTHON_PATH=C:\Users\Administrator\AppData\Local\Programs\Python\Python312"
set "PROJECT_PATH=%~dp0"
:: 末尾不要带反斜杠
set "PROJECT_PATH=%PROJECT_PATH:~0,-1%"
set "VENV_DIR=%PROJECT_PATH%\venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "VENV_PYI=%VENV_DIR%\Scripts\pyinstaller.exe"
set "PIP_INSTALL_LOG=%PROJECT_PATH%\pip_install.log"
set "PIP_UPGRADE_LOG=%PROJECT_PATH%\pip_upgrade.log"

:: ====== 0. 检查 Python 3.9 是否存在 ======
if not exist "%PYTHON_PATH%\python.exe" (
    echo [错误] 找不到 Python 3.9: %PYTHON_PATH%\python.exe
    goto :error
)

:: ====== 1. 创建虚拟环境（已存在则跳过）======
if not exist "%VENV_PY%" (
    echo 正在创建虚拟环境...
    "%PYTHON_PATH%\python.exe" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败！
        goto :error
    )
) else (
    echo 虚拟环境已存在，跳过创建。
)

:: ====== 2. 升级 venv 里的 pip / setuptools / wheel ======
echo 正在升级 pip / setuptools / wheel...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel > "%PIP_UPGRADE_LOG%" 2>&1
if errorlevel 1 (
    echo [错误] pip 升级失败！查看 pip_upgrade.log
    type "%PIP_UPGRADE_LOG%"
    goto :error
)

:: ====== 3. 安装依赖（输出进日志，失败时打印）======
echo 正在安装依赖...
"%VENV_PY%" -m pip install -r "%PROJECT_PATH%\requirements.txt" > "%PIP_INSTALL_LOG%" 2>&1
if errorlevel 1 (
    echo [错误] 依赖安装失败！完整日志见 pip_install.log
    echo ---------------- pip_install.log ----------------
    type "%PIP_INSTALL_LOG%"
    echo -----------------------------------------------
    echo %date% %time% 依赖安装失败 >> "%PROJECT_PATH%\error_log.txt"
    goto :error
)

:: ====== 4. 在 venv 里确认 pyinstaller 可用 ======
if not exist "%VENV_PYI%" (
    echo [错误] venv 中未找到 pyinstaller，检查 requirements.txt 是否包含 pyinstaller
    goto :error
)

:: ====== 5. 打包 ======
echo 开始编译...
"%VENV_PYI%" "%PROJECT_PATH%\build.spec" --clean --log-level ERROR 2> "%PROJECT_PATH%\error_log.txt"
if errorlevel 1 (
    echo [错误] 编译失败！查看 error_log.txt
    type "%PROJECT_PATH%\error_log.txt"
    goto :error
)

:: ====== 6. 复制配置文件 & 生成启动脚本 ======
echo 复制配置文件...
copy "%PROJECT_PATH%\config.json"        "%PROJECT_PATH%\dist\smallbolt2\" >nul 2>&1
copy "%PROJECT_PATH%\sample.config.json" "%PROJECT_PATH%\dist\smallbolt2\" >nul 2>&1

echo 生成启动脚本...
(
    echo @echo off
    echo cd /d "%%~dp0smallbolt2"
    echo start "" smallbolt2.exe
) > "%PROJECT_PATH%\dist\run.bat"

echo 编译成功！输出目录: %PROJECT_PATH%\dist\smallbolt2
exit /b 0

:error
echo 编译过程中断！日志: error_log.txt / pip_install.log / pip_upgrade.log
endlocal
exit /b 1