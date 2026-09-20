# M6 companion / buddy smoke
$ErrorActionPreference = "Stop"
$Base = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$PhoneA = "13800138201"
$PhoneB = "13800138202"

function Invoke-Json {
    param([string]$Method, [string]$Url, [hashtable]$Headers = @{}, [object]$Body = $null)
    $params = @{ Method = $Method; Uri = $Url; Headers = $Headers; ContentType = "application/json" }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress) }
    return Invoke-RestMethod @params
}

function Login-User([string]$Phone, [string]$Device) {
    Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/send" -Body @{ phone = $Phone } | Out-Null
    $login = Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/login" -Body @{
        phone = $Phone; code = "123456"; device_id = $Device; platform = "android"
    }
    return @{
        Token = $login.data.tokens.access_token
        UserId = [string]$login.data.user.id
        Auth = @{ Authorization = "Bearer $($login.data.tokens.access_token)" }
    }
}

Write-Host "== login =="
$a = Login-User $PhoneA "smoke-m6-a"
$b = Login-User $PhoneB "smoke-m6-b"

Write-Host "== buddy intent =="
Invoke-Json -Method PUT -Url "$Base/api/v1/me/buddy-intent" -Headers $a.Auth -Body @{
    text = "找周末爬山搭子"; tags = @("hiking"); city = "上海"; active = $true
} | Out-Null
$feed = Invoke-Json -Method GET -Url "$Base/api/v1/buddies/feed?limit=10" -Headers $b.Auth
Write-Host "feed total=$($feed.data.page_info.total)"

Write-Host "== greet =="
Invoke-Json -Method POST -Url "$Base/api/v1/buddies/$($a.UserId)/greet" -Headers $b.Auth -Body @{
    text = "你好呀"
} | Out-Null

Write-Host "== companion apply + admin approve =="
Invoke-Json -Method POST -Url "$Base/api/v1/companions/apply" -Headers $a.Auth -Body @{
    service_type = "offline"; specialty = "户外向导"; intro = "烟雾测试陪玩"; city = "上海"
} | Out-Null
$adminLogin = Invoke-Json -Method POST -Url "$Base/admin/v1/auth/login" -Body @{
    username = "admin"; password = "Admin@123456"
}
$adminAuth = @{ Authorization = "Bearer $($adminLogin.data.access_token)" }
Invoke-Json -Method POST -Url "$Base/admin/v1/companions/$($a.UserId)/review" -Headers $adminAuth -Body @{
    action = "approve"
} | Out-Null

Write-Host "== service + slot =="
$svc = Invoke-Json -Method POST -Url "$Base/api/v1/me/companion-profile/services" -Headers $a.Auth -Body @{
    title = "半日徒步"; pricing_unit = "session"; price_cents = 19900; min_units = 1
}
$start = (Get-Date).ToUniversalTime().AddDays(2).ToString("o")
$end = (Get-Date).ToUniversalTime().AddDays(2).AddHours(3).ToString("o")
$slot = Invoke-Json -Method POST -Url "$Base/api/v1/me/companion-profile/slots" -Headers $a.Auth -Body @{
    start_at = $start; end_at = $end
}

Write-Host "== booking =="
$h = @{
    Authorization = "Bearer $($b.Token)"
    "Idempotency-Key" = "smoke-m6-booking-1"
}
$booking = Invoke-Json -Method POST -Url "$Base/api/v1/bookings" -Headers $h -Body @{
    companion_id = $a.UserId
    service_id = $svc.data.id
    slot_id = $slot.data.id
    units = 1
}
$orderId = $booking.data.order.id
$pay = Invoke-Json -Method POST -Url "$Base/api/v1/orders/$orderId/pay" -Headers $b.Auth -Body @{ method = "wallet" }
if ($pay.data.order.status -ne "paid") { throw "pay failed" }

$bookingId = $booking.data.id
Invoke-Json -Method POST -Url "$Base/api/v1/bookings/$bookingId/start" -Headers $a.Auth | Out-Null
Invoke-Json -Method POST -Url "$Base/api/v1/bookings/$bookingId/complete" -Headers $a.Auth | Out-Null

Write-Host "== leaderboard =="
$lb = Invoke-Json -Method GET -Url "$Base/api/v1/companions/leaderboard?period=week" -Headers $b.Auth
Write-Host "leaderboard items=$(($lb.data.items | Measure-Object).Count)"

Write-Host ""
Write-Host "smoke_m6 OK"
