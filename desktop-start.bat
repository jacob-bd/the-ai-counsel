@echo off
setlocal
cd /d "%~dp0"

if not exist node_modules (
  echo Installing desktop dependencies...
  call npm install
  if errorlevel 1 exit /b %errorlevel%
)

if not exist frontend\node_modules (
  echo Installing frontend dependencies...
  call npm install --prefix frontend
  if errorlevel 1 exit /b %errorlevel%
)

echo Starting The AI Counsel desktop wrapper...
call npm run desktop:start
