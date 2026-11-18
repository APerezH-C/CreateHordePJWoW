@echo off
rem Builds dist\BotWow.exe: installs the build requirements and packages
rem loop.py with BotWow.spec (PyInstaller, one windowed file).
setlocal
cd /d "%~dp0"

echo [1/2] Installing the build requirements (requirements-build.txt)...
python -m pip install --disable-pip-version-check -r requirements-build.txt || goto :fail

echo [2/2] Building with PyInstaller...
python -m PyInstaller --noconfirm --clean BotWow.spec || goto :fail

echo.
echo Done: %~dp0dist\BotWow.exe
exit /b 0

:fail
echo.
echo ERROR: the build failed.
exit /b 1
