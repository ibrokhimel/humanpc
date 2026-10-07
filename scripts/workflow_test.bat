@echo off
REM End-to-end workflow test in a local browser page (navigate, click, type, scroll,
REM dropdown, checkboxes, slider drag, submit). Drives the REAL mouse and keyboard.
REM Abort with Ctrl+Alt+Q.
REM
REM   workflow_test.bat                      bot, trained movement model
REM   workflow_test.bat --mouse hil          bot, built-in movement engine
REM   workflow_test.bat --runs 5
REM   workflow_test.bat --mode human         record YOUR baseline
REM   workflow_test.bat score                compare all runs so far

setlocal
set "REPO=%~dp0.."
pushd "%REPO%"
set "PYTHONPATH=%CD%;%PYTHONPATH%"

python -c "import keyboard" 2>nul || python -m pip install keyboard

if /I "%~1"=="score" (
    python winval\workflow\score_workflow.py --json captures\workflow\report.json
) else (
    python winval\workflow\run_workflow.py %*
)
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
