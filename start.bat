@echo off
rem BotWow from source: installs Pillow (requirements.txt) if it is missing,
rem then starts the bot. Extra arguments are passed on, e.g. start.bat --dry-run
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :nopython

rem Pillow 12.1 or newer (the bot needs Image.get_flattened_data).
python -c "from PIL import Image; Image.Image.get_flattened_data" >nul 2>nul
if not errorlevel 1 goto :run
echo Installing the requirements (requirements.txt)...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :fail

:run
python loop.py --autostart %*
if errorlevel 1 pause
exit /b 0

:nopython
echo Python was not found.
echo Install Python 3.12 from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH" in the installer, then run start.bat again.
pause
exit /b 1

:fail
echo.
echo ERROR: the requirements could not be installed.
pause
exit /b 1
