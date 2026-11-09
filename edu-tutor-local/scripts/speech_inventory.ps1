param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$voice = New-Object -ComObject SAPI.SpVoice
try {
    $sapi = @($voice.GetVoices() | ForEach-Object {
        @{ id=$_.Id; name=$_.GetDescription(); language=$_.GetAttribute('Language'); vendor=$_.GetAttribute('Vendor') }
    })
} finally { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($voice) | Out-Null }
$winrtCommand = '[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime] | Out-Null; @([Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | ForEach-Object { @{ id=$_.Id; name=$_.DisplayName; language=$_.Language; gender=$_.Gender.ToString(); description=$_.Description } }) | ConvertTo-Json -Depth 6'
$winrtJson = & "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -Command $winrtCommand
if ($LASTEXITCODE -ne 0) { throw 'WinRT voice enumeration failed' }
$winrt = @($winrtJson | ConvertFrom-Json)
$binary = Join-Path $env:WINDIR 'System32/Speech/Common/sapi.dll'
$hostPath = (Get-Process -Id $PID).Path
$report = @{ at=[DateTime]::UtcNow.ToString('o'); sapi=$sapi; winrt=$winrt;
    synthesis_attempts=0; engine_binary=$binary; engine_version=(Get-Item -LiteralPath $binary).VersionInfo.FileVersion;
    sapi_binary_sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLower();
    os_build=[Environment]::OSVersion.Version.ToString(); local_inventory_only=$true;
    powershell_executable=$hostPath; powershell_sha256=(Get-FileHash -LiteralPath $hostPath -Algorithm SHA256).Hash.ToLower();
    powershell_policy=(Get-ExecutionPolicy).ToString(); powershell_version=$PSVersionTable.PSVersion.ToString() }
[IO.File]::WriteAllText($OutputPath, ($report | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
$report | ConvertTo-Json -Depth 8
