@echo off
chcp 65001 > NUL
title テレ東BIZダイジェスト 手動同期ツール
cd /d "%~dp0"
.\.venv\Scripts\python.exe txbiz_digest_collector.py
pause
