# M2 smoke: login -> profile -> discover -> swipe -> mutual match -> chat token (noop)
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"

function Login([string]$phone) {
  try {
    $body = '{"phone":"' + $phone + '"}'
    Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/send" -ContentType "application/json" -Body $body | Out-Null
  } catch {
    # Dev login accepts fixed code even if send is rate-limited
  }
  $body = '{"phone":"' + $phone + '","code":"123456","device_id":"m2-smoke","platform":"android"}'
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/login" -ContentType "application/json" -Body $body
  return $login.data.tokens.access_token
}

function PutProfile([string]$token, [string]$name, [string]$gender) {
  $body = '{"display_name":"' + $name + '","birthday":"1999-01-01","gender":"' + $gender + '","city":"Shanghai","bio":"m2 smoke","tags":["travel"]}'
  Invoke-RestMethod -Method Put -Uri "$base/api/v1/me/profile" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json; charset=utf-8" -Body $body | Out-Null
}

$suffix = Get-Date -Format "HHmmss"
$phoneA = "138" + $suffix.PadLeft(8, "0")
$phoneB = "139" + $suffix.PadLeft(8, "0")

Write-Host "== login A female phone=$phoneA =="
$tokenA = Login $phoneA
PutProfile $tokenA "TestA" "female"
Write-Host "ok"

Write-Host "== login B male phone=$phoneB =="
$tokenB = Login $phoneB
PutProfile $tokenB "TestB" "male"
$meB = Invoke-RestMethod -Method Get -Uri "$base/api/v1/me" -Headers @{ Authorization = "Bearer $tokenB" }
$idB = $meB.data.id
Write-Host "userB=$idB"

Write-Host "== B likes A =="
$meA = Invoke-RestMethod -Method Get -Uri "$base/api/v1/me" -Headers @{ Authorization = "Bearer $tokenA" }
$idA = $meA.data.id
$key2 = [guid]::NewGuid().ToString()
$body = '{"target_user_id":"' + $idA + '","action":"like","idempotency_key":"' + $key2 + '"}'
$likeBA = Invoke-RestMethod -Method Post -Uri "$base/api/v1/swipes" -Headers @{ Authorization = "Bearer $tokenB" } -ContentType "application/json" -Body $body
Write-Host ("matched=" + $likeBA.data.matched)

Write-Host "== A likes B expect match =="
$key3 = [guid]::NewGuid().ToString()
$body = '{"target_user_id":"' + $idB + '","action":"like","idempotency_key":"' + $key3 + '"}'
$likeAB = Invoke-RestMethod -Method Post -Uri "$base/api/v1/swipes" -Headers @{ Authorization = "Bearer $tokenA" } -ContentType "application/json" -Body $body
Write-Host ("matched=" + $likeAB.data.matched + " match_id=" + $likeAB.data.match.id)
if (-not $likeAB.data.matched) { throw "expected mutual match" }
$matchId = $likeAB.data.match.id

Write-Host "== cards for A exclude matched B =="
$cards = Invoke-RestMethod -Method Get -Uri "$base/api/v1/discover/cards?limit=10" -Headers @{ Authorization = "Bearer $tokenA" }
Write-Host ("card_count=" + $cards.data.items.Count)
$hasB = @($cards.data.items | Where-Object { $_.id -eq $idB })
if ($hasB.Count -gt 0) { throw "matched peer still in feed" }
if ($cards.data.items.Count -lt 1) { throw "no cards for A" }
$demo = $cards.data.items[0].id
Write-Host "demo_target=$demo"

Write-Host "== A pass demo =="
$key1 = [guid]::NewGuid().ToString()
$body = '{"target_user_id":"' + $demo + '","action":"pass","idempotency_key":"' + $key1 + '"}'
$pass = Invoke-RestMethod -Method Post -Uri "$base/api/v1/swipes" -Headers @{ Authorization = "Bearer $tokenA" } -ContentType "application/json" -Body $body
Write-Host ("recorded=" + $pass.data.recorded)

Write-Host "== cards again demo excluded =="
$cards2 = Invoke-RestMethod -Method Get -Uri "$base/api/v1/discover/cards?limit=20" -Headers @{ Authorization = "Bearer $tokenA" }
$again = @($cards2.data.items | Where-Object { $_.id -eq $demo })
if ($again.Count -gt 0) { throw "swiped user still in feed" }
Write-Host ("card_count=" + $cards2.data.items.Count)

Write-Host "== matches list =="
$matches = Invoke-RestMethod -Method Get -Uri "$base/api/v1/matches" -Headers @{ Authorization = "Bearer $tokenA" }
Write-Host ("match_count=" + $matches.data.items.Count)

Write-Host "== chat token noop reserved =="
$body = '{"match_id":"' + $matchId + '"}'
$chat = Invoke-RestMethod -Method Post -Uri "$base/api/v1/chat/token" -Headers @{ Authorization = "Bearer $tokenA" } -ContentType "application/json" -Body $body
Write-Host ("provider=" + $chat.data.provider + " ready=" + $chat.data.ready)
if ($chat.data.provider -ne "noop") { throw "expected noop IM provider" }

Write-Host "M2 SMOKE OK"
