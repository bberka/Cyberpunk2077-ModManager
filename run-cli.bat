@echo off
setlocal
cd /d "%~dp0"
python cli_entry.py %*
