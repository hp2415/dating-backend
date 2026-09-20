# M7 trust smoke
$ErrorActionPreference = "Stop"
$Base = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$Phone = "13800138301"

function Invoke-Json {
    param([string]$Method, [string]$Url, [hashtable]$Headers = @{}, [object]$Body = $null)
    $params = @{ Method = $Method; Uri = $Url; Headers = $Headers; ContentType = "application/json" }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress) }
    return Invoke-RestMethod @params
}

Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/send" -Body @{ phone = $Phone } | Out-Null
$login = Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/login" -Body @{
    phone = $Phone; code = "123456"; device_id = "smoke-m7"; platform = "android"
}
$auth = @{ Authorization = "Bearer $($login.data.tokens.access_token)" }
$userId = [string]$login.data.user.id

Write-Host "== me/trust =="
$trust = Invoke-Json -Method GET -Url "$Base/api/v1/me/trust" -Headers $auth
Write-Host "level=$($trust.data.level) confidence_low=$($trust.data.confidence_low)"

Write-Host "== photo verification =="
$v = Invoke-Json -Method POST -Url "$Base/api/v1/verifications/photo" -Headers $auth -Body @{
    similarity = 0.95; quality_score = 0.9
}
Write-Host "verification=$($v.data.status)"

Write-Host "== trust event =="
Invoke-Json -Method POST -Url "$Base/api/v1/trust/events" -Headers $auth -Body @{
    name = "profile_completed"; domain = "account"; value = 2; note = "smoke"
} | Out-Null

Write-Host "== public trust =="
$pub = Invoke-Json -Method GET -Url "$Base/api/v1/users/$userId/trust" -Headers $auth
if ($null -eq $pub.data.badges) { throw "missing badges" }

Write-Host "== admin =="
$adminLogin = Invoke-Json -Method POST -Url "$Base/admin/v1/auth/login" -Body @{
    username = "admin"; password = "Admin@123456"
}
$adminAuth = @{ Authorization = "Bearer $($adminLogin.data.access_token)" }
$scores = Invoke-Json -Method GET -Url "$Base/admin/v1/trust/scores?limit=5" -Headers $adminAuth
if (-not $scores.data.page_info) { throw "missing page_info" }

Write-Host "smoke_m7 OK"
