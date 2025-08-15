@echo off
python -m src.main_orchestrator config/config.development.yaml
echo Exit code: %ERRORLEVEL%
pause
exit /b