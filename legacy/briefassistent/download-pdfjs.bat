@echo off
REM Ga naar de map waar dit script staat (voorkomt C:\Windows probleem bij UNC paden)
cd /d "%~dp0"

echo ============================================
echo   PDF.js downloaden voor BriefAssistent
echo ============================================
echo.
echo Script-locatie: %~dp0
echo.

if not exist "pdfjs" mkdir pdfjs

echo Downloaden van pdf.min.js...
powershell -Command "Invoke-WebRequest -Uri 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js' -OutFile '%~dp0pdfjs\pdf.min.js'"

echo Downloaden van pdf.worker.min.js...
powershell -Command "Invoke-WebRequest -Uri 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js' -OutFile '%~dp0pdfjs\pdf.worker.min.js'"

if exist "%~dp0pdfjs\pdf.min.js" (
    echo.
    echo ============================================
    echo   OK! PDF.js succesvol gedownload in:
    echo   %~dp0pdfjs\
    echo   U kunt de extensie nu laden in Edge.
    echo ============================================
) else (
    echo.
    echo FOUT: Download mislukt. Controleer uw internetverbinding.
)

echo.
pause
