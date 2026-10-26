@echo off
REM One-command run for Windows: double-click this file, or type run_all in a Command Prompt.
REM It runs run_all.ps1 without needing to change PowerShell's script execution policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_all.ps1" %*
pause
