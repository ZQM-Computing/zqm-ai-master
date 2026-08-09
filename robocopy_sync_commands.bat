@echo off
setlocal enabledelayedexpansion
set SRC=C:\Users\zqmco\Desktop\enhance-repos\zqm-ai-master
set DEST=C:\Void\ZQM-AI-Master
echo Syncing from "%SRC%" to "%DEST%" ...
robocopy "%SRC%" "%DEST%" /E /PURGE /NFL /NDL /NP /R:3 /W:2 /XD .git .pytest_cache .ruff_cache /XF *.pyc /LOG+:C:\Void\ZQM-AI-Master\robocopy_sync.log
if %ERRORLEVEL% LEQ 7 (
  echo Robocopy completed.
  exit /b 0
) else (
  echo Robocopy failed with level %ERRORLEVEL%.
  exit /b %ERRORLEVEL%
)
