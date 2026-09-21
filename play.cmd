@echo off
rem Runs jev-zork inside WSL (Ubuntu) from Windows.
rem   play install                    first time: uv, Python, Jericho, ROM, tests
rem   play --mock --steps 20          no key: random draw, this is NOT Jev
rem   play --delay 0.6 --steps 150    with TYPESAFE_API_KEY in .env
rem Another WSL distribution: set JEV_ZORK_WSL=Debian
setlocal
if "%JEV_ZORK_WSL%"=="" set "JEV_ZORK_WSL=Ubuntu"
if /I "%~1"=="install" (
  wsl.exe -d %JEV_ZORK_WSL% --cd "%~dp0." --exec bash scripts/setup_wsl.sh
) else (
  wsl.exe -d %JEV_ZORK_WSL% --cd "%~dp0." --exec bash scripts/play.sh %*
)
exit /b %ERRORLEVEL%
