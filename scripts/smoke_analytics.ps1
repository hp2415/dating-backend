# Analytics ingest smoke: batch accept, event_id dedupe, oversize batch rejected, rate limit.
$ErrorActionPreference = "Stop"
$Base = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }

function New-Event {
    param(
        [string]$EventId,
        [string]$Name = "app.launched",
        [string]$AnonId = "smoke-anon"
    )
    return @{
        event_id = $EventId
        event_name = $Name
        anon_id = $AnonId
        session_id = "smoke-session"
        screen = "smoke"
        props = @{ cold_start = "true" }
        occurred_at = (Get-Date).ToUniversalTime().ToString("o")
        platform = "android"
        app_version = "smoke"
        build_type = "debug"
        os_version = "test"
        device_model = "script"
        network_type = "wifi"
    }
}

function ConvertTo-EventBatch {
    param([object[]]$Events)
    $parts = foreach ($event in $Events) {
        ($event | ConvertTo-Json -Depth 6 -Compress)
    }
    return '{"events":[' + ($parts -join ",") + ']}'
}

function Invoke-Api {
    param(
        [string]$Method,
        [string]$Url,
        [string]$JsonBody = $null
    )
    $bodyFile = $null
    $tmp = New-TemporaryFile
    try {
        $curlArgs = @("-sS", "-X", $Method, "-H", "Content-Type: application/json", "-w", "`n%{http_code}", "-o", $tmp.FullName)
        if ($JsonBody) {
            $bodyFile = New-TemporaryFile
            [System.IO.File]::WriteAllText($bodyFile.FullName, $JsonBody, [System.Text.UTF8Encoding]::new($false))
            $curlArgs += @("--data-binary", "@$($bodyFile.FullName)")
        }
        $curlArgs += $Url
        $statusLine = & curl.exe @curlArgs
        $status = [int]($statusLine | Select-Object -Last 1)
        $text = Get-Content -Raw -Path $tmp.FullName
        $parsed = $null
        if ($text) { $parsed = $text | ConvertFrom-Json }
        return @{ Status = $status; Json = $parsed; Raw = $text }
    } finally {
        Remove-Item -Force $tmp.FullName -ErrorAction SilentlyContinue
        if ($bodyFile) { Remove-Item -Force $bodyFile.FullName -ErrorAction SilentlyContinue }
    }
}

Write-Host "== health =="
$health = Invoke-Api -Method GET -Url "$Base/health"
if ($health.Status -ne 200 -or $health.Json.code -ne 0) {
    throw "health failed: $($health.Raw)"
}

$id1 = [guid]::NewGuid().ToString()
$id2 = [guid]::NewGuid().ToString()
$anon = "smoke-" + [guid]::NewGuid().ToString()

Write-Host "== accept batch =="
$first = Invoke-Api -Method POST -Url "$Base/api/v1/analytics/events" -JsonBody (ConvertTo-EventBatch @(
    (New-Event -EventId $id1 -AnonId $anon),
    (New-Event -EventId $id2 -Name "auth.login_viewed" -AnonId $anon)
))
if ($first.Status -ne 200 -or $first.Json.code -ne 0) { throw "ingest failed: $($first.Raw)" }
if ($first.Json.data.accepted -ne 2 -or $first.Json.data.duplicated -ne 0) {
    throw "expected accepted=2 duplicated=0, got $($first.Raw)"
}

Write-Host "== dedupe =="
$again = Invoke-Api -Method POST -Url "$Base/api/v1/analytics/events" -JsonBody (ConvertTo-EventBatch @(
    (New-Event -EventId $id1 -AnonId $anon),
    (New-Event -EventId $id2 -Name "auth.login_viewed" -AnonId $anon)
))
if ($again.Status -ne 200 -or $again.Json.code -ne 0) { throw "dedupe ingest failed: $($again.Raw)" }
if ($again.Json.data.accepted -ne 0 -or $again.Json.data.duplicated -ne 2) {
    throw "expected accepted=0 duplicated=2, got $($again.Raw)"
}

Write-Host "== unknown event still accepted =="
$unknownId = [guid]::NewGuid().ToString()
$unknown = Invoke-Api -Method POST -Url "$Base/api/v1/analytics/events" -JsonBody (ConvertTo-EventBatch @(
    (New-Event -EventId $unknownId -Name "smoke.unknown_event" -AnonId $anon)
))
if ($unknown.Json.code -ne 0 -or $unknown.Json.data.accepted -ne 1) {
    throw "unknown event should be stored: $($unknown.Raw)"
}

Write-Host "== batch over 50 rejected =="
$tooMany = @()
for ($i = 0; $i -lt 51; $i++) {
    $tooMany += New-Event -EventId ([guid]::NewGuid().ToString()) -AnonId $anon
}
$over = Invoke-Api -Method POST -Url "$Base/api/v1/analytics/events" -JsonBody (ConvertTo-EventBatch $tooMany)
if ($over.Status -ne 422 -or $over.Json.code -ne 90002) {
    throw "expected 422 validation, got status=$($over.Status) body=$($over.Raw)"
}

Write-Host "== rate limit =="
$limited = $false
for ($i = 0; $i -lt 70; $i++) {
    $hit = Invoke-Api -Method POST -Url "$Base/api/v1/analytics/events" -JsonBody (ConvertTo-EventBatch @(
        (New-Event -EventId ([guid]::NewGuid().ToString()) -AnonId $anon)
    ))
    if ($hit.Status -eq 429 -and $hit.Json.code -eq 10004) {
        $limited = $true
        Write-Host "limited after $($i + 1) extra requests in this loop"
        break
    }
    if ($hit.Json.code -ne 0) {
        throw "unexpected during rate loop: $($hit.Raw)"
    }
}
if (-not $limited) { throw "rate limit did not trip within 70 requests" }

Write-Host ""
Write-Host "smoke_analytics OK"
