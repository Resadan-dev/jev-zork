@echo off
rem Lance jev-zork dans WSL (Ubuntu) depuis Windows.
rem   jouer installer                 premiere fois : uv, Python, Jericho, ROM, tests
rem   jouer --mock --steps 20         sans cle : tirage au hasard, ce n'est PAS Jev
rem   jouer --delay 0.6 --steps 150   avec TYPESAFE_API_KEY dans .env
rem Autre distribution WSL : set JEV_ZORK_WSL=Debian
setlocal
if "%JEV_ZORK_WSL%"=="" set "JEV_ZORK_WSL=Ubuntu"
if /I "%~1"=="installer" (
  wsl.exe -d %JEV_ZORK_WSL% --cd "%~dp0." --exec bash scripts/setup_wsl.sh
) else (
  wsl.exe -d %JEV_ZORK_WSL% --cd "%~dp0." --exec bash scripts/play.sh %*
)
exit /b %ERRORLEVEL%
