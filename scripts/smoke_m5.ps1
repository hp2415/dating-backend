# M5 messaging smoke: conversations / friends / transfers / calls / admin read
$ErrorActionPreference = "Stop"
$Base = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$PhoneA = "13800138101"
$PhoneB = "13800138102"

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

function Login-User([string]$Phone, [string]$Device) {
    Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/send" -Body @{ phone = $Phone } | Out-Null
    $login = Invoke-Json -Method POST -Url "$Base/api/v1/auth/sms/login" -Body @{
        phone = $Phone
        code = "123456"
        device_id = $Device
        platform = "android"
    }
    return @{
        Token = $login.data.tokens.access_token
        UserId = $login.data.user.id
        Auth = @{ Authorization = "Bearer $($login.data.tokens.access_token)" }
    }
}

Write-Host "== health =="
$health = Invoke-Json -Method GET -Url "$Base/health"
if (-not $health.data.im) { throw "health missing im" }
Write-Host "im=$($health.data.im | ConvertTo-Json -Compress) version=$($health.data.version)"

Write-Host "== login A/B =="
$a = Login-User $PhoneA "smoke-m5-a"
$b = Login-User $PhoneB "smoke-m5-b"
Write-Host "A=$($a.UserId) B=$($b.UserId)"

Write-Host "== public uid =="
$uidA = Invoke-Json -Method GET -Url "$Base/api/v1/me/public-uid" -Headers $a.Auth
$uidB = Invoke-Json -Method GET -Url "$Base/api/v1/me/public-uid" -Headers $b.Auth
if (-not $uidA.data.public_uid) { throw "missing public_uid A" }
Write-Host "uidA=$($uidA.data.public_uid) uidB=$($uidB.data.public_uid)"

Write-Host "== chat status / token =="
$status = Invoke-Json -Method GET -Url "$Base/api/v1/chat/status"
if ($status.data.provider -ne "noop") { throw "expected noop provider" }
$token = Invoke-Json -Method POST -Url "$Base/api/v1/chat/token" -Headers $a.Auth -Body @{}
if (-not $token.data.token) { throw "missing chat token" }
Write-Host "token_ready=$($token.data.ready)"

Write-Host "== open direct =="
$dm = Invoke-Json -Method POST -Url "$Base/api/v1/conversations/direct" -Headers $a.Auth -Body @{
    peer_user_id = $b.UserId
    preview = "你好，冒烟测试"
}
if (-not $dm.data.id) { throw "direct conversation missing id" }
$convId = $dm.data.id
Write-Host "direct=$convId kind=$($dm.data.kind)"

Write-Host "== list conversations =="
$list = Invoke-Json -Method GET -Url "$Base/api/v1/conversations?limit=20" -Headers $a.Auth
if (-not $list.data.page_info) { throw "conversations missing page_info" }

Write-Host "== friend request by uid =="
$fr = Invoke-Json -Method POST -Url "$Base/api/v1/friend-requests" -Headers $a.Auth -Body @{
    to_uid = $uidB.data.public_uid
    message = "加个好友"
    source = "uid"
}
$frId = $fr.data.id
$incoming = Invoke-Json -Method GET -Url "$Base/api/v1/friend-requests?direction=incoming" -Headers $b.Auth
if (($incoming.data.items | Measure-Object).Count -lt 1) { throw "no incoming friend request" }
$accept = Invoke-Json -Method POST -Url "$Base/api/v1/friend-requests/$frId/respond" -Headers $b.Auth -Body @{
    action = "accept"
}
Write-Host "friend accept=$($accept.data.status)"

$friends = Invoke-Json -Method GET -Url "$Base/api/v1/friends" -Headers $a.Auth
if (($friends.data.items | Measure-Object).Count -lt 1) { throw "friends empty after accept" }

Write-Host "== create group =="
$group = Invoke-Json -Method POST -Url "$Base/api/v1/conversations/group" -Headers $a.Auth -Body @{
    title = "冒烟群"
    member_ids = @($b.UserId)
}
$groupId = $group.data.id
Write-Host "group=$groupId"

Write-Host "== call =="
$call = Invoke-Json -Method POST -Url "$Base/api/v1/calls" -Headers $a.Auth -Body @{
    conversation_id = $convId
    callee_id = $b.UserId
    kind = "voice"
}
$callId = $call.data.id
Invoke-Json -Method POST -Url "$Base/api/v1/calls/$callId/answer" -Headers $b.Auth | Out-Null
$ended = Invoke-Json -Method POST -Url "$Base/api/v1/calls/$callId/end" -Headers $a.Auth
Write-Host "call status=$($ended.data.status)"

Write-Host "== transfer (needs wallet balance) =="
# Top up A then transfer to B
$hTop = @{
    Authorization = "Bearer $($a.Token)"
    "Idempotency-Key" = "smoke-m5-topup-1"
}
try {
    Invoke-Json -Method POST -Url "$Base/api/v1/me/wallet/topup" -Headers $hTop -Body @{
        amount_cents = 500
        method = "wechat"
    } | Out-Null
} catch {
    Write-Host "topup skipped/failed (ok if already funded): $($_.Exception.Message)"
}
$xfer = Invoke-Json -Method POST -Url "$Base/api/v1/transfers" -Headers $a.Auth -Body @{
    conversation_id = $convId
    to_user_id = $b.UserId
    amount_cents = 100
}
$xferId = $xfer.data.id
$accepted = Invoke-Json -Method POST -Url "$Base/api/v1/transfers/$xferId/accept" -Headers $b.Auth
Write-Host "transfer=$($accepted.data.status)"

Write-Host "== lookup by uid =="
$lookup = Invoke-Json -Method GET -Url "$Base/api/v1/users/by-uid/$($uidB.data.public_uid)" -Headers $a.Auth
if ($lookup.data.id -ne $b.UserId) { throw "uid lookup mismatch" }

Write-Host "== admin messaging =="
$adminLogin = Invoke-Json -Method POST -Url "$Base/admin/v1/auth/login" -Body @{
    username = "admin"
    password = "Admin@123456"
}
$adminAuth = @{ Authorization = "Bearer $($adminLogin.data.access_token)" }
$adminConvs = Invoke-Json -Method GET -Url "$Base/admin/v1/conversations?limit=5" -Headers $adminAuth
if (-not $adminConvs.data.page_info) { throw "admin conversations missing page_info" }
$adminFriends = Invoke-Json -Method GET -Url "$Base/admin/v1/friendships?limit=5" -Headers $adminAuth
if (-not $adminFriends.data.page_info) { throw "admin friendships missing page_info" }

Write-Host ""
Write-Host "smoke_m5 OK"
