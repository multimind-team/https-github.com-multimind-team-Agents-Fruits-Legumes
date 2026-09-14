@echo off
setlocal
cd /d "%~dp0"
rem Sans option : execute le filet, qui peut recalculer les donnees derivees.
rem --verifier : lecture seule. --forcer : recalcul explicite.
rem Ce lanceur ne prouve ni completude metier ni surveillance automatique.
set "SILENCIEUX="
set "OPTIONS="
:arguments
if "%~1"=="" goto executer
if /I "%~1"=="--silencieux" (
  set "SILENCIEUX=1"
) else if /I "%~1"=="--verifier" (
  set "OPTIONS=%OPTIONS% --verifier"
) else if /I "%~1"=="--forcer" (
  set "OPTIONS=%OPTIONS% --forcer"
) else (
  echo Option inconnue. Options : --verifier --forcer --silencieux
  exit /b 2
)
shift
goto arguments
:executer
py -3.14 "%~dp0moteur\filet-de-securite.py" %OPTIONS%
set "RESULTAT=%ERRORLEVEL%"
echo.
if not defined SILENCIEUX pause
exit /b %RESULTAT%
