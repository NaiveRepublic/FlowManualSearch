@echo off
setlocal
cd /d "%~dp0"
title Flow Manual Search - build
echo.
echo  Flow Manual Search - building FlowManualSearch.exe
echo  ---------------------------------------------------
echo.

rem --- find Python (3.12 preferred) ---
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "1" >nul 2>nul
  if not errorlevel 1 set "PY=py -3.12"
)
if defined PY goto :havepy
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :havepy
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :havepy
echo  Python was not found.
echo  Install Python 3.12 from https://www.python.org/downloads/windows/
echo  and tick "Add python.exe to PATH" during installation. Then run this file again.
goto :fail

:havepy
echo  Using: %PY%

rem --- private environment so nothing else on the PC is affected ---
if not exist ".venv\Scripts\python.exe" (
  echo  Creating build environment...
  %PY% -m venv .venv || goto :fail
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip --quiet || goto :fail
echo  Installing build tools, the first run takes a few minutes...
"%VPY%" -m pip install -r requirements-app.txt --quiet || goto :fail

rem --- optional: new manual dragged onto this file ---
if "%~1"=="" goto :skipindex
echo  Rebuilding the search index from the new manual...
"%VPY%" -m pip install -r requirements-index.txt --quiet || goto :fail
"%VPY%" build_tools\build_index.py "%~1" || goto :fail
"%VPY%" build_tools\eval_queries.py
:skipindex

echo  Checking the search engine...
"%VPY%" app\main.py --selftest >nul || goto :fail

echo  Packaging the .exe...
"%VPY%" -m PyInstaller --noconfirm --clean FlowManualSearch.spec || goto :fail

echo.
echo  Done:  %cd%\dist\FlowManualSearch.exe
echo.
explorer "%cd%\dist"
pause
exit /b 0

:fail
echo.
echo  Build stopped. The messages above say what went wrong.
pause
exit /b 1
