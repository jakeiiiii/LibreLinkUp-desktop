@echo off
echo Cleaning build artifacts...

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
del /f /q *.spec 2>nul

echo Cleaning Python cache...
for /d /r %%i in (__pycache__) do if exist "%%i" rmdir /s /q "%%i"
del /s /q *.pyc 2>nul
del /s /q *.pyo 2>nul

echo Cleaning eggs and wheels...
for /d /r %%i in (*.egg-info) do if exist "%%i" rmdir /s /q "%%i"
del /s /q *.egg 2>nul
del /s /q *.whl 2>nul
if exist .eggs rmdir /s /q .eggs

echo Cleaning virtual environments...
if exist venv rmdir /s /q venv
if exist .venv rmdir /s /q .venv
if exist env rmdir /s /q env

echo Cleaning IDE files...
if exist .vscode rmdir /s /q .vscode
if exist .idea rmdir /s /q .idea
del /s /q *.swp 2>nul
del /s /q *.swo 2>nul

echo Cleaning OS junk...
del /s /q Thumbs.db 2>nul
del /s /q Desktop.ini 2>nul

echo Cleaning Claude Code...
if exist .claude rmdir /s /q .claude

echo Done. Ready for git push.
