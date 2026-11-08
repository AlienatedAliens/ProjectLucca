 = New-Object -ComObject WScript.Shell
 = [Environment]::GetFolderPath('Desktop')
 = .CreateShortcut(" \Project Lucca.lnk\)
.TargetPath = \C:\projects\ProjectLucca\launch_lucca.bat\
.WorkingDirectory = \C:\projects\ProjectLucca\
.IconLocation = \C:\projects\ProjectLucca\assets\icon.ico\
.Description = \Project Lucca -- Chrono Trigger Desktop AI Companion\
.Save()
Write-Host \Desktop shortcut created at \Project Lucca.lnk\
