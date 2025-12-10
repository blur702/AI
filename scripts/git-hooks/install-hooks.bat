@echo off
REM Install Git Hooks
REM Run from project root: scripts\git-hooks\install-hooks.bat

echo Installing git hooks...

REM Create hooks directory if it doesn't exist
if not exist ".git\hooks" mkdir ".git\hooks"

REM Copy post-merge hook
copy /Y "scripts\git-hooks\post-merge" ".git\hooks\post-merge"

echo.
echo Git hooks installed successfully!
echo.
echo The post-merge hook will automatically index changed files to Weaviate
echo after every git merge/pull operation.
echo.
pause
