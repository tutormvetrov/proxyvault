@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare-portable-seed.ps1" %*
