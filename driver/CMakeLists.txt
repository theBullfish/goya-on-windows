# CMakeLists.txt for goya_bar KMDF driver
#
# This is primarily for IDE support (IntelliSense, etc.)
# Actual build uses MSBuild via the WDK project system.
#
# To build:
#   1. Install Visual Studio 2022 with C++ Desktop Development
#   2. Install Windows Driver Kit (WDK)
#   3. Open goya_bar.vcxproj in Visual Studio
#   4. Build for Release x64
#
# Or from command line:
#   msbuild goya_bar.vcxproj /p:Configuration=Release /p:Platform=x64

cmake_minimum_required(VERSION 3.20)
project(goya_bar C)

# WDK include paths (adjust for your WDK installation)
set(WDK_ROOT "C:/Program Files (x86)/Windows Kits/10")
set(WDK_VERSION "10.0.26100.0")

add_library(goya_bar SHARED
    goya_bar.c
    goya_bar.h
)
