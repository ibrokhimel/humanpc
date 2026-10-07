@echo off
REM Live demo: open Microsoft Paint from the Start menu and draw a coloured apple.
REM Drives the REAL mouse and keyboard. Abort with Ctrl+Alt+Q (or slam the pointer
REM into a screen corner for the failsafe).

setlocal
set "REPO=%~dp0.."
pushd "%REPO%"

set "PYTHONPATH=%CD%;%PYTHONPATH%"
set "HUMANPC_LIVE=1"

REM Optional deps: mss = screenshot capture, keyboard = global Ctrl+Alt+Q kill-switch.
python -c "import mss, keyboard" 2>nul || python -m pip install mss keyboard

echo.
echo Running the Paint apple demo - keep hands off the mouse.
echo.
python tests\test_paint_apple_live.py
set "RC=%ERRORLEVEL%"

popd
echo.
if "%RC%"=="0" (echo Done - see captures\paint_apple.png) else (echo FAILED with exit code %RC%)
pause
exit /b %RC%
