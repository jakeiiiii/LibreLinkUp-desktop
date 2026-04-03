@echo off
echo Cleaning build artifacts...

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist LibreLinkUp.spec del /f /q LibreLinkUp.spec

echo Cleaning __pycache__ directories...
for /d /r %%i in (__pycache__) do if exist "%%i" rmdir /s /q "%%i"

echo Cleaning .pyc files...
del /s /q *.pyc 2>nul

echo Done. Ready for git push.
