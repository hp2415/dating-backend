# M4 commerce smoke: wallet / order / stub pay / refund / membership / credentials
$ErrorActionPreference = "Stop"
$Base = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$Phone = "13800138099"

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
Write-Host "payment=$($health.data.payment | ConvertTo-Json -Compress) im=$($health.data.im | ConvertTo-Json -Compress)"

Write-Host "== sms login =="
Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/send" -Body @{ phone = $Phone } | Out-Null
$login = Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/login" -Body @{
    phone = $Phone
    code = "123456"
    device_id = "smoke-m4"
    platform = "android"
}
$token = $login.data.tokens.access_token
$auth = @{ Authorization = "Bearer $token" }

Write-Host "== wallet =="
$wallet = Invoke-Json -Method GET -Url "$Base/api/v1/me/wallet" -Headers $auth
Write-Host "balance=$($wallet.data.balance_display)"

Write-Host "== topup stub wechat =="
$hTop = @{
    Authorization = "Bearer $token"
    "Idempotency-Key" = "smoke-topup-1"
}
$topup = Invoke-Json -Method POST -Url "$Base/api/v1/me/wallet/topup" -Headers $hTop -Body @{
    amount_cents = 1000
    method = "wechat"
}
if ($topup.data.order.status -ne "paid") { throw "topup not paid: $($topup.data.order.status)" }
Write-Host "topup order=$($topup.data.order.order_no) status=$($topup.data.order.status)"

$wallet2 = Invoke-Json -Method GET -Url "$Base/api/v1/me/wallet" -Headers $auth
Write-Host "balance after topup=$($wallet2.data.balance_display)"

Write-Host "== membership subscribe wallet =="
$hVip = @{
    Authorization = "Bearer $token"
    "Idempotency-Key" = "smoke-vip-1"
}
$sub = Invoke-Json -Method POST -Url "$Base/api/v1/membership/subscribe" -Headers $hVip -Body @{
    plan_code = "monthly"
    method = "wallet"
}
if ($sub.data.order.status -ne "paid") { throw "subscribe not paid" }
Write-Host "vip=$($sub.data.membership.plan_code) expires=$($sub.data.membership.expires_at)"

Write-Host "== companion booking stub order =="
$hOrd = @{
    Authorization = "Bearer $token"
    "Idempotency-Key" = "smoke-booking-1"
}
$order = Invoke-Json -Method POST -Url "$Base/api/v1/orders" -Headers $hOrd -Body @{
    kind = "companion_booking"
    subject_title = "演示陪玩 1 小时"
    amount_cents = 5000
}
$pay = Invoke-Json -Method POST -Url "$Base/api/v1/orders/$($order.data.id)/pay" -Headers $auth -Body @{
    method = "wallet"
}
if ($pay.data.order.status -ne "paid") { throw "booking pay failed" }
Write-Host "booking paid order_no=$($pay.data.order.order_no)"

Write-Host "== refund =="
$rf = Invoke-Json -Method POST -Url "$Base/api/v1/refunds" -Headers $auth -Body @{
    order_id = $order.data.id
    reason = "行程变更"
    detail = "smoke_m4"
}
if ($rf.data.status -ne "completed") { throw "refund not completed: $($rf.data.status)" }
Write-Host "refund=$($rf.data.status) amount=$($rf.data.amount_display)"

Write-Host "== credentials =="
$creds = Invoke-Json -Method GET -Url "$Base/api/v1/me/credentials?limit=10" -Headers $auth
Write-Host "credentials=$($creds.data.page_info.total)"

Write-Host "== admin orders =="
$adminLogin = Invoke-Json -Method POST -Url "$Base/admin/v1/auth/login" -Body @{
    username = "admin"
    password = "Admin@123456"
}
$adminAuth = @{ Authorization = "Bearer $($adminLogin.data.access_token)" }
$adminOrders = Invoke-Json -Method GET -Url "$Base/admin/v1/orders?limit=5" -Headers $adminAuth
if (-not $adminOrders.data.page_info) { throw "admin orders missing page_info" }

Write-Host ""
Write-Host "smoke_m4 OK"
