@echo off
rem Arranque do Personal Wealth Manager (ficheiro generico, sem dados pessoais)
title Personal Wealth Manager
set "RAIZ=%~dp0.."
set "PY=%LOCALAPPDATA%\pwm\venv\Scripts\python.exe"
set "PORTA=8000"

if not exist "%PY%" (echo [ERRO] Ambiente Python nao encontrado em %PY% & pause & exit /b 1)

cd /d "%RAIZ%"

echo A guardar copia de seguranca do estado anterior...
"%PY%" -m app.backup
echo.

echo A abrir http://127.0.0.1:%PORTA%
echo Para fechar: botao "Guardar e sair" na aplicacao (faz a copia de seguranca final).
echo Se fechares por Ctrl+C ou no X, a copia fica garantida no proximo arranque.
echo.
start "" /min cmd /c "ping -n 3 127.0.0.1 >nul & start http://127.0.0.1:%PORTA%"
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORTA%
if errorlevel 1 (echo. & echo [ERRO] A aplicacao terminou com erro. & pause)
