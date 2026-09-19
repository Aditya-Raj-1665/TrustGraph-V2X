@echo off
setlocal
if not exist "%~dp0midsem\index.html" (
  echo The presentation package has not been built yet.
  echo Run the midsem build command in README.md first.
  pause
  exit /b 1
)
start "" "%~dp0midsem\index.html"
endlocal
