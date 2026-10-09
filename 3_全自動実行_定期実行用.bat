@echo off
chcp 65001 > NUL
title テレ東BIZダイジェスト 自動同期
cd /d "%~dp0"
.\.venv\Scripts\python.exe txbiz_digest_collector.py --auto
pause
