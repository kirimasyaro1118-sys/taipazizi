@echo off
chcp 65001 > NUL
cd /d "%~dp0"
.\.venv\Scripts\python.exe txbiz_news_sync.py
