@echo off
REM Windows BAT script to manage the publishing of the arduino-hid-emulator package

REM Define variables
set PACKAGE_NAME=arduino-hid-emulator
set PYPI_REPO=pypi
set TEST_PYPI_REPO=testpypi
set DIST_DIR=dist

REM Parse argument and jump to the appropriate section
if "%1"=="" goto menu
if "%1"=="clean" goto clean
if "%1"=="build" goto build
if "%1"=="test-publish" goto test-publish
if "%1"=="publish" goto publish
if "%1"=="test-install" goto test-install
if "%1"=="test" goto test

REM Invalid argument handling
echo Invalid command: %1
goto menu

:clean
echo Cleaning up old builds...
if exist %DIST_DIR% (
    rmdir /s /q %DIST_DIR%
    echo %DIST_DIR% folder removed.
) else (
    echo %DIST_DIR% folder already clean.
)
if exist build (
    rmdir /s /q build
    echo build folder removed.
) else (
    echo build folder already clean.
)
for /d %%D in (*.egg-info) do (
    rmdir /s /q "%%D"
    echo Removed %%D
) || echo No .egg-info folders found.
exit /b

:build
call :clean
echo Building the package...
python setup.py sdist bdist_wheel
if %ERRORLEVEL% neq 0 (
    echo Error: Package build failed.
    exit /b 1
)
exit /b

:test-publish
call :build
echo Publishing to TestPyPI...
twine upload --repository %TEST_PYPI_REPO% %DIST_DIR%\*
if %ERRORLEVEL% neq 0 (
    echo Error: Publishing to TestPyPI failed.
    exit /b 1
)
exit /b

:publish
call :build
echo Publishing to PyPI...
twine upload --repository %PYPI_REPO% %DIST_DIR%\*
if %ERRORLEVEL% neq 0 (
    echo Error: Publishing to PyPI failed.
    exit /b 1
)
exit /b

:test-install
echo Installing from TestPyPI...
pip install --index-url https://test.pypi.org/simple/ --no-deps %PACKAGE_NAME%
if %ERRORLEVEL% neq 0 (
    echo Error: Test installation failed.
    exit /b 1
)
exit /b

:test
python -m pytest -q
exit /b %ERRORLEVEL%

:menu
echo Usage: manage_package.bat [command]
echo Available commands:
echo   clean          - Remove old builds
echo   build          - Build the package
echo   test-publish   - Publish to TestPyPI
echo   publish        - Publish to PyPI
echo   test-install   - Install from TestPyPI
echo   test           - Local pytest checks only (no publishing)
exit /b
