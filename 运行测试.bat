@echo off
chcp 65001 >nul
cd /d %~dp0
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"
"%PYEXE%" -m pytest tests -v
echo.
echo 上面结果中：passed=通过，failed=失败，error=环境或代码报错。
pause
