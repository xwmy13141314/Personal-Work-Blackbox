@echo off
:: Clean stale DB auxiliary files
if exist "E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\data\blackbox.db-wal" del /f "E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\data\blackbox.db-wal"
if exist "E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\data\blackbox.db-shm" del /f "E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\data\blackbox.db-shm"
if exist "E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\data\blackbox.db-journal" del /f "E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\data\blackbox.db-journal"

:: Copy new exe
copy /Y "C:\Users\Thinkpad\AppData\Local\Temp\wt_dist5\WorkTrace.exe" "E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\dist\WorkTrace.exe"

echo DONE > "C:\Users\Thinkpad\AppData\Local\Temp\wt_deploy5_done.txt"
