@echo off
setlocal
cd /d "%~dp0"

echo =====================================================================
echo  Rayon Fruits et Legumes - Recuperation Autonome du Prospectus
echo  Intermarche Contact / Super Carmaux
echo =====================================================================
echo.

echo [WINDOWS] Lancement du script autonome : moteur\chercher-et-envoyer-prospectus.py
echo.

py -3.14 -B "%~dp0moteur\chercher-et-envoyer-prospectus.py" %*
set "CODE_RETOUR=%ERRORLEVEL%"

echo.
echo =====================================================================
if %CODE_RETOUR% equ 0 (
    echo [SUCCES] Recherche et envoi termines avec succes ^(Code 0^).
) else (
    echo [ATTENTION] Le script s'est termine avec le code erreur : %CODE_RETOUR%
)
echo =====================================================================
echo.

set "EST_SILENCIEUX=0"
for %%A in (%*) do (
    if "%%A"=="--silencieux" set "EST_SILENCIEUX=1"
    if "%%A"=="--cron" set "EST_SILENCIEUX=1"
)

if "%EST_SILENCIEUX%"=="0" (
    echo Appuyez sur une touche pour fermer cette fenetre...
    pause >nul
)

exit /b %CODE_RETOUR%
