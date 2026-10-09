$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Set-ScheduledTask -TaskName "TxBizNewsAutoSync" -Settings $st
$info = Get-ScheduledTask -TaskName "TxBizNewsAutoSync" | Get-ScheduledTaskInfo
Write-Host "Task Name:" "TxBizNewsAutoSync"
Write-Host "Next Run Time:" $info.NextRunTime
Write-Host "Last Run Time:" $info.LastRunTime
Write-Host "Last Task Result:" $info.LastTaskResult
