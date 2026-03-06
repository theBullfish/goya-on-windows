@echo off
REM Run this as Administrator to install the Goya BAR driver
REM Right-click -> Run as administrator

echo ============================================
echo  Goya BAR Driver Installation
echo ============================================
echo.

REM Check admin
net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Must run as Administrator!
    echo Right-click this file and choose "Run as administrator"
    pause
    exit /b 1
)

REM Add cert to trusted root and trusted publishers
echo Installing test certificate to Trusted Root and Publishers...
certutil -addstore Root "D:\goya-on-windows\driver\build\GoyaTest.cer" 2>nul
certutil -addstore TrustedPublisher "D:\goya-on-windows\driver\build\GoyaTest.cer" 2>nul

REM Enable test signing
echo.
echo Enabling test signing...
bcdedit /set testsigning on

REM Install driver
echo.
echo Installing driver...
pnputil /add-driver "D:\goya-on-windows\driver\build\stage\goya_bar.inf" /install

echo.
echo ============================================
echo  Installation complete!
echo  REBOOT may be required for test signing.
echo  After reboot, run: python -m goya
echo ============================================
pause
