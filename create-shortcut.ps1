# This script creates a Start Menu shortcut for launching/developing The AI Counsel desktop app

$targetPath = "x:\Code\the-ai-counsel-main-test\desktop-start.bat"
$shortcutDir = [System.IO.Path]::Combine([System.Environment]::GetFolderPath('StartMenu'), 'Programs')
$shortcutPath = [System.IO.Path]::Combine($shortcutDir, "The AI Counsel Dev.lnk")

$wshell = New-Object -ComObject WScript.Shell
$shortcut = $wshell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = "x:\Code\the-ai-counsel-main-test"
$shortcut.Description = "Launch The AI Counsel Desktop App (Dev)"
$shortcut.Save()

Write-Host "Start Menu shortcut created at: $shortcutPath"
