@echo off
chcp 65001 > NUL
title テレ東BIZダイジェスト Webダッシュボード起動
cd /d "%~dp0"
echo ========================================================
echo  テレ東BIZダイジェスト 2分動画まとめシステム
echo  Webダッシュボードを起動しています...
echo ========================================================
echo.
echo ブラウザで http://localhost:8000 を開きます...
start http://localhost:8000
.\.venv\Scripts\python.exe server.py
pause
