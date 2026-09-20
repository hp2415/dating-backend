# M8 ops / config smoke: taxonomies, shelves, push-token, announcements, feedback
$ErrorActionPreference = "Stop"
$Base = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$Phone = "13800138808"

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
Invoke-Json -Method GET -Url "$Base/health" | Out-Null

Write-Host "== sms login =="
Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/send" -Body @{ phone = $Phone } | Out-Null
$login = Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/login" -Body @{
    phone = $Phone
    code = "123456"
    device_id = "smoke-m8"
    platform = "android"
}
$token = $login.data.tokens.access_token
$auth = @{ Authorization = "Bearer $token" }

Write-Host "== taxonomies =="
$tax = Invoke-Json -Method GET -Url "$Base/api/v1/taxonomies?kind=activity_category" -Headers $auth
if (-not $tax.data.items) { throw "taxonomies empty — ensure seed ran" }
Write-Host "activity_category count=$(( $tax.data.items | Measure-Object ).Count)"

Write-Host "== discover shelves =="
$shelves = Invoke-Json -Method GET -Url "$Base/api/v1/discover/shelves?city=上海" -Headers $auth
Write-Host "shelves count=$(( $shelves.data.items | Measure-Object ).Count)"

Write-Host "== push token =="
$pt = Invoke-Json -Method POST -Url "$Base/api/v1/me/push-token" -Headers $auth -Body @{
    device_id = "smoke-m8"
    platform = "android"
    provider = "fcm"
    token = "smoke-fcm-token-m8"
}
if (-not $pt.data.device_id) { throw "push token missing device_id" }
Write-Host "push device=$($pt.data.device_id) provider=$($pt.data.provider)"

Write-Host "== announcements =="
$anns = Invoke-Json -Method GET -Url "$Base/api/v1/announcements?limit=10" -Headers $auth
if (-not $anns.data.page_info) { throw "announcements missing page_info" }
Write-Host "announcements total=$($anns.data.page_info.total)"

Write-Host "== feedback =="
$fb = Invoke-Json -Method POST -Url "$Base/api/v1/feedbacks" -Headers $auth -Body @{
    category = "general"
    content = "M8 smoke feedback"
    contact = $Phone
}
if (-not $fb.data.id) { throw "feedback missing id" }
Write-Host "feedback=$($fb.data.id) status=$($fb.data.status)"

Write-Host "== admin taxonomy list =="
$adminLogin = Invoke-Json -Method POST -Url "$Base/admin/v1/auth/login" -Body @{
    username = "admin"
    password = "Admin@123456"
}
$adminAuth = @{ Authorization = "Bearer $($adminLogin.data.access_token)" }
$adminTax = Invoke-Json -Method GET -Url "$Base/admin/v1/taxonomies" -Headers $adminAuth
if (-not $adminTax.data.items) { throw "admin taxonomies empty" }
Write-Host "admin taxonomies=$(( $adminTax.data.items | Measure-Object ).Count)"

Write-Host ""
Write-Host "smoke_m8 OK"
