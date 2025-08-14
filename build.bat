@echo off
REM Build and Push to Docker Hub Script for Windows
REM Usage: build-and-push.bat [version_tag]

setlocal enabledelayedexpansion

REM Configuration
set DOCKER_USERNAME=infyrus
set IMAGE_NAME=rbl-sourcing-portal
if "%1"=="" (
    set VERSION=latest
) else (
    set VERSION=%1
)

echo 🚀 Building and pushing RBL Sourcing Portal...
echo Image: %DOCKER_USERNAME%/%IMAGE_NAME%:%VERSION%

REM Build the image
echo 📦 Building Docker image...
docker build -t %DOCKER_USERNAME%/%IMAGE_NAME%:%VERSION% .

if errorlevel 1 (
    echo ❌ Build failed!
    exit /b 1
)

REM Tag as latest if not already
if not "%VERSION%"=="latest" (
    docker tag %DOCKER_USERNAME%/%IMAGE_NAME%:%VERSION% %DOCKER_USERNAME%/%IMAGE_NAME%:latest
)

REM Login to Docker Hub
echo 🔑 Logging in to Docker Hub...
docker login

if errorlevel 1 (
    echo ❌ Login failed!
    exit /b 1
)

REM Push the image
echo ⬆️ Pushing to Docker Hub...
docker push %DOCKER_USERNAME%/%IMAGE_NAME%:%VERSION%

if errorlevel 1 (
    echo ❌ Push failed!
    exit /b 1
)

if not "%VERSION%"=="latest" (
    docker push %DOCKER_USERNAME%/%IMAGE_NAME%:latest
)

echo ✅ Successfully pushed %DOCKER_USERNAME%/%IMAGE_NAME%:%VERSION% to Docker Hub!
echo.
echo To deploy, update your compose.yml with:
echo   image: %DOCKER_USERNAME%/%IMAGE_NAME%:%VERSION%
echo.
echo Then run: docker-compose up -d

endlocal
