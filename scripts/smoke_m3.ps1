# M3 foundation smoke: pagination shape, domain events, RBAC, worker heartbeat
$ErrorActionPreference = "Stop"
$Base = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }

function Invoke-Json {
    param(
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        [object]$Body = $null
    )
    $params = @{
        Method = $Method
        Uri = $Url
        Headers = $Headers
        ContentType = "application/json"
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress)
    }
    return Invoke-RestMethod @params
}

Write-Host "== health =="
$health = Invoke-Json -Method GET -Url "$Base/health"
if ($health.code -ne 0) { throw "health failed: $($health | ConvertTo-Json -Compress)" }
Write-Host "postgres=$($health.data.postgres.ok) postgis=$($health.data.postgres.postgis) worker=$($health.data.worker.ok)"

Write-Host "== admin login =="
$login = Invoke-Json -Method POST -Url "$Base/admin/v1/auth/login" -Body @{
    username = "admin"
    password = "Admin@123456"
}
$token = $login.data.access_token
if (-not $token) { throw "no admin token" }
$auth = @{ Authorization = "Bearer $token" }

Write-Host "== auth/me permissions =="
$me = Invoke-Json -Method GET -Url "$Base/admin/v1/auth/me" -Headers $auth
if ($me.data.role -ne "superadmin") { throw "expected superadmin" }
if (-not ($me.data.permissions -contains "*")) { throw "expected * permission" }

Write-Host "== enqueue domain event =="
$ev = Invoke-Json -Method POST -Url "$Base/admin/v1/ops/domain-events" -Headers $auth -Body @{
    name = "ops.ping"
    aggregate_kind = "ops"
    aggregate_id = "smoke-m3"
    payload = @{ source = "smoke_m3.ps1" }
}
$eventId = $ev.data.id
Write-Host "event id=$eventId status=$($ev.data.status)"

Write-Host "== list domain events (page_info) =="
$list = Invoke-Json -Method GET -Url "$Base/admin/v1/ops/domain-events?limit=5&offset=0" -Headers $auth
if (-not $list.data.page_info) { throw "missing page_info" }
if ($null -eq $list.data.total) { throw "missing legacy total" }
Write-Host "total=$($list.data.total) has_more=$($list.data.page_info.has_more)"

Write-Host "== activities list page_info =="
$acts = Invoke-Json -Method GET -Url "$Base/admin/v1/activities?status=all&limit=5&offset=0" -Headers $auth
if (-not $acts.data.page_info) { throw "activities missing page_info" }

Write-Host "== event handlers inventory =="
$handlers = Invoke-Json -Method GET -Url "$Base/admin/v1/ops/event-handlers" -Headers $auth
if ($handlers.data.items.Count -lt 1) { throw "no handlers" }

Write-Host ""
Write-Host "smoke_m3 OK — wait ~15s for worker to drain ops.ping (status -> done)"
Write-Host "Re-check: GET $Base/admin/v1/ops/domain-events"
