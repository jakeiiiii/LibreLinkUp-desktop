@echo off
echo Building LibreLinkUp Desktop...
pyinstaller --noconfirm --onedir --windowed ^
    --name "LibreLinkUp" ^
    --add-data "resources;resources" ^
    main.py
echo.
echo Zipping dist\LibreLinkUp to bin\LibreLinkUp.zip...
if not exist bin mkdir bin
if exist bin\LibreLinkUp.zip del /f /q bin\LibreLinkUp.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\LibreLinkUp\*' -DestinationPath 'bin\LibreLinkUp.zip'"
echo.
echo Build complete! Output in bin\LibreLinkUp.zip
pause
