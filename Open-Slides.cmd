@echo off
setlocal
if not exist "%~dp0midsem\slides.html" (
  echo The presentation package has not been built yet.
  pause
  exit /b 1
)
start "" "%~dp0midsem\slides.html"
endlocal
