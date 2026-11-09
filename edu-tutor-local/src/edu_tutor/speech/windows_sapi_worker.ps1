param([Parameter(Mandatory=$true)][string]$RequestPath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$voice = $null
$stream = $null
$opened = $false
$watch = [Diagnostics.Stopwatch]::StartNew()
$outcome = 'failed'
function Write-Stage([string]$Name) {
    if ($null -eq $request -or -not $request.progress_path) { return }
    $entry = @{ stage=$Name; process_id=$PID; parent_pid=$request.parent_pid; job_id=$request.job_id;
        elapsed_seconds=$watch.Elapsed.TotalSeconds; timestamp=[DateTime]::UtcNow.ToString('o') }
    [IO.File]::AppendAllText($request.progress_path, ($entry | ConvertTo-Json -Compress) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}
try {
    $request = Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Stage 'process_started'
    $spec = $request.spec
    if ($spec.provider -ne 'windows_sapi_local' -or $spec.language -ne 'ko-KR' -or $spec.sample_rate -ne 22050) { throw 'Invalid SAPI request contract' }
    if (Test-Path -LiteralPath $request.cancel_path) { throw 'Cancelled before synthesis' }
    if (Test-Path -LiteralPath $request.output) { throw 'Output already exists' }
    while (-not (Test-Path -LiteralPath $request.ownership_ready)) {
        if ($watch.Elapsed.TotalSeconds -gt 10 -or (Test-Path -LiteralPath $request.cancel_path)) { throw 'Parent did not establish owned process job' }
        Start-Sleep -Milliseconds 10
    }
    Write-Stage 'ownership_confirmed'
    $voice = New-Object -ComObject SAPI.SpVoice
    $selected = @($voice.GetVoices() | Where-Object { $_.Id -ceq $spec.voice })
    if ($selected.Count -ne 1 -or -not ($selected[0].GetAttribute('Language').ToLower().Split(';') -contains '412')) { throw 'Exact installed Korean voice unavailable' }
    $voice.Voice = $selected[0]
    $voice.Rate = [int]$spec.rate
    $voice.Volume = [int]$spec.volume
    $stream = New-Object -ComObject SAPI.SpFileStream
    $stream.Format.Type = 22 # SAFT22kHz16BitMono: PCM 22050Hz / 16bit / mono.
    $stream.Open($request.output, 3, $false)
    $opened = $true
    $voice.AllowAudioOutputFormatChangesOnNextSet = $false
    $voice.AudioOutputStream = $stream
    Write-Stage 'engine_ready'
    $synthWatch = [Diagnostics.Stopwatch]::StartNew()
    # Async + literal text. Never treat student text as XML or a filename.
    $streamNumber = $voice.Speak([string]$spec.spoken_text, 17)
    Write-Stage 'synth_queued'
    do {
        $parent = Get-Process -Id ([int]$request.parent_pid) -ErrorAction Stop
        $unix = ([DateTimeOffset]$parent.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds() / 1000.0
        if ([Math]::Abs($unix - [double]$request.parent_create_time) -gt 0.1) { throw 'Owning Python process identity changed' }
        if ((Test-Path -LiteralPath $request.cancel_path) -or $watch.Elapsed.TotalSeconds -gt [double]$request.max_seconds) { throw 'Cancelled or bounded SAPI deadline' }
        $done = $voice.WaitUntilDone(50)
    } while (-not $done)
    $synthWatch.Stop()
    Write-Stage 'synth_finished'
    $stream.Close()
    $opened = $false
    $result = @{ finish_reason='sapi_wait_until_done'; voice_id=$selected[0].Id; language='ko-KR';
        stream_number=$streamNumber; synthesis_seconds=$synthWatch.Elapsed.TotalSeconds;
        initialization_seconds=$watch.Elapsed.TotalSeconds-$synthWatch.Elapsed.TotalSeconds;
        process_id=$PID; parent_pid=[int]$request.parent_pid; api='SAPI.SpVoice.Speak/WaitUntilDone';
        transport='installed local COM engine; no network calls'; literal_text=$true }
    [IO.File]::WriteAllText($request.report, ($result | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
    $outcome = 'completed'
} catch {
    Write-Stage 'failed_or_cancelled'
    if ($null -ne $voice) { try { $voice.Speak('', 19) | Out-Null } catch {} }
    [Console]::Error.WriteLine($_.Exception.ToString())
    exit 1
} finally {
    if ($opened) { try { $stream.Close() } catch {} }
    if ($null -ne $stream) { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($stream) | Out-Null }
    if ($null -ne $voice) { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($voice) | Out-Null }
    Write-Stage ('closed_' + $outcome)
}
