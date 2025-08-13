@echo off
python -m src.main_orchestrator config/config.default.yaml
echo Exit code: %ERRORLEVEL%
pause
exit /b