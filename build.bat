@echo off
echo Building LibreLinkUp Desktop...
pyinstaller --noconfirm --onedir --windowed ^
    --name "LibreLinkUp" ^
    --add-data "resources;resources" ^
    main.py
echo.
echo Build complete! Output in dist\LibreLinkUp\
pause
