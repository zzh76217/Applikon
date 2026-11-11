@echo off
chcp 65001 >nul
cd /d %~dp0
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"
"%PYEXE%" run.py
if errorlevel 1 (
  echo.
  echo [启动失败] 请把上方报错信息截图发给开发者，不要反复双击。
  pause
)
