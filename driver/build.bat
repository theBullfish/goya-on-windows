@echo off
REM Build goya_bar.sys KMDF driver
REM Requires: VS Build Tools + WDK 10.0.26100

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  Goya BAR Driver Build
echo ============================================

REM Find vcvarsall.bat
set "VCVARS="
if exist "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if "!VCVARS!"=="" if exist "C:\Program Files\Microsoft Visual Studio\2026\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=C:\Program Files\Microsoft Visual Studio\2026\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if "!VCVARS!"=="" if exist "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if "!VCVARS!"=="" if exist "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if "!VCVARS!"=="" (
    echo ERROR: Cannot find vcvarsall.bat. Install VS Build Tools first.
    exit /b 1
)

echo Found VC: !VCVARS!
call "!VCVARS!" amd64

REM Find WDK
set "WDK_ROOT=C:\Program Files (x86)\Windows Kits\10"
if not exist "!WDK_ROOT!\Include\wdf" (
    echo ERROR: WDK not found at !WDK_ROOT!\Include\wdf
    echo Install WDK: winget install Microsoft.WindowsWDK.10.0.26100
    exit /b 1
)

REM Find WDK version
set "WDK_VER="
for /d %%D in ("!WDK_ROOT!\Include\*") do (
    if exist "%%D\km" set "WDK_VER=%%~nxD"
)
if "!WDK_VER!"=="" (
    echo ERROR: Cannot find WDK version
    exit /b 1
)
echo WDK Version: !WDK_VER!

REM Find KMDF version
set "KMDF_VER="
for /d %%D in ("!WDK_ROOT!\Include\wdf\kmdf\*") do (
    set "KMDF_VER=%%~nxD"
)
if "!KMDF_VER!"=="" (
    echo ERROR: Cannot find KMDF version
    exit /b 1
)
echo KMDF Version: !KMDF_VER!

set "WDK_INC=!WDK_ROOT!\Include\!WDK_VER!"
set "WDK_LIB=!WDK_ROOT!\Lib\!WDK_VER!"
set "KMDF_INC=!WDK_ROOT!\Include\wdf\kmdf\!KMDF_VER!"
set "KMDF_LIB=!WDK_ROOT!\Lib\wdf\kmdf\x64\!KMDF_VER!"

echo.
echo Include paths:
echo   KM:   !WDK_INC!\km
echo   KMDF: !KMDF_INC!
echo   Lib:  !WDK_LIB!\km\x64
echo.

REM Create output directory
if not exist "build" mkdir build

echo Compiling goya_bar.c...
cl.exe /nologo /kernel /GS- /W4 /Zi /Od ^
    /D "NTDDI_VERSION=0x0A000000" ^
    /D "_WIN64" /D "_AMD64_" /D "AMD64" ^
    /D "KMDF_VERSION_MAJOR=1" /D "KMDF_VERSION_MINOR=33" ^
    /I "!WDK_INC!\km" ^
    /I "!WDK_INC!\km\crt" ^
    /I "!WDK_INC!\shared" ^
    /I "!KMDF_INC!" ^
    /Fo"build\goya_bar.obj" ^
    /c goya_bar.c

if errorlevel 1 (
    echo ERROR: Compilation failed
    exit /b 1
)

echo Linking goya_bar.sys...
link.exe /nologo /DRIVER:WDM /SUBSYSTEM:NATIVE /ENTRY:FxDriverEntry ^
    /OUT:"build\goya_bar.sys" ^
    /PDB:"build\goya_bar.pdb" ^
    /NODEFAULTLIB ^
    /LIBPATH:"!WDK_LIB!\km\x64" ^
    /LIBPATH:"!KMDF_LIB!" ^
    ntoskrnl.lib hal.lib wdmsec.lib BufferOverflowK.lib ^
    WdfDriverEntry.lib WdfLdr.lib ^
    build\goya_bar.obj

if errorlevel 1 (
    echo ERROR: Linking failed
    exit /b 1
)

echo.
echo ============================================
echo  BUILD SUCCESS: build\goya_bar.sys
echo ============================================
echo.
echo Next steps:
echo   1. Enable test signing:  bcdedit /set testsigning on  (reboot)
echo   2. Self-sign the driver: signtool sign /fd SHA256 /f test.pfx build\goya_bar.sys
echo   3. Install:              pnputil /add-driver goya_bar.inf /install
echo   4. Verify:               sc query GoyaBAR
echo   5. Run probe:            cd .. ^&^& set PYTHONPATH=src ^&^& python -m goya
