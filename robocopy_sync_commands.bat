@echo off
setlocal enabledelayedexpansion
set SRC=C:\Users\zqmco\Desktop\enhance-repos\zqm-ai-master
set DEST=C:\Void\ZQM-AI-Master
echo Syncing from "%SRC%" to "%DEST%" ...
robocopy "%SRC%" "%DEST%" *.* /NDL /NFL /S /E /DCOPY:DA /COPY:DAT /PURGE /NP /R:3 /W:2
echo Robocopy completed.
pause