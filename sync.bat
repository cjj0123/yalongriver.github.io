@echo off
:: 自动获取管理员权限
%1 mshta vbscript:CreateObject("Shell.Application").ShellExecute("cmd.exe","/c %~s0 ::","","runas",1)(window.close)&&exit
cd /d "%~dp0"

echo [1/3] Adding changes...
git add .

echo [2/3] Committing...
set msg=Auto-update %date% %time%
git commit -m "%msg%"

echo [3/3] Pushing to GitHub...
git push origin main

echo Sync Complete!
pause