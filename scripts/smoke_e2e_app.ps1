# End-to-end app smoke (W4-3): login -> profile -> activity -> post -> wallet topup
# Requires local/staging API with SMS_ALLOW_DEV_CODE and seed admin.
$ErrorActionPreference = "Stop"
$base = if ($env:API_BASE) { $env:API_BASE.TrimEnd("/") } else { "http://localhost:8000" }

function Login([string]$phone) {
  try {
    Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/send" -ContentType "application/json" -Body ("{`"phone`":`"$phone`"}") | Out-Null
  } catch {}
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/login" -ContentType "application/json" `
    -Body ("{`"phone`":`"$phone`",`"code`":`"123456`",`"device_id`":`"e2e-smoke`",`"platform`":`"android`"}")
  return $login.data.tokens.access_token
}

function AdminToken() {
  $admin = Invoke-RestMethod -Method Post -Uri "$base/admin/v1/auth/login" -ContentType "application/json" `
    -Body '{"username":"admin","password":"Admin@123456"}'
  return $admin.data.access_token
}

$suffix = Get-Date -Format "HHmmss"
$phoneA = "136" + $suffix.PadLeft(8, "0")
$phoneB = "137" + $suffix.PadLeft(8, "0")

Write-Host "== base=$base =="
Write-Host "== login A/B =="
$tokenA = Login $phoneA
$tokenB = Login $phoneB

Write-Host "== profiles =="
Invoke-RestMethod -Method Put -Uri "$base/api/v1/me/profile" -Headers @{ Authorization = "Bearer $tokenA" } -ContentType "application/json" `
  -Body '{"display_name":"E2E-A","birthday":"1998-01-01","gender":"female","city":"Shanghai","bio":"e2e","tags":["sport"]}' | Out-Null
Invoke-RestMethod -Method Put -Uri "$base/api/v1/me/profile" -Headers @{ Authorization = "Bearer $tokenB" } -ContentType "application/json" `
  -Body '{"display_name":"E2E-B","birthday":"1997-01-01","gender":"male","city":"Shanghai","bio":"e2e","tags":["food"]}' | Out-Null

Write-Host "== create + approve activity =="
$act = Invoke-RestMethod -Method Post -Uri "$base/api/v1/activities" -Headers @{ Authorization = "Bearer $tokenA" } -ContentType "application/json" `
  -Body '{"title":"E2E weekend hike","description":"e2e","category":"outdoors","city":"Shanghai","capacity":6,"media":[]}'
$aid = $act.data.id
$admin = AdminToken
Invoke-RestMethod -Method Post -Uri "$base/admin/v1/activities/$aid/review" -Headers @{ Authorization = "Bearer $admin" } -ContentType "application/json" `
  -Body '{"action":"approve"}' | Out-Null
Invoke-RestMethod -Method Post -Uri "$base/api/v1/activities/$aid/join" -Headers @{ Authorization = "Bearer $tokenB" } | Out-Null

Write-Host "== create + approve post =="
$post = Invoke-RestMethod -Method Post -Uri "$base/api/v1/community/posts" -Headers @{ Authorization = "Bearer $tokenB" } -ContentType "application/json" `
  -Body '{"content":"E2E post hello","media":[]}'
$pid = $post.data.id
Invoke-RestMethod -Method Post -Uri "$base/admin/v1/community/posts/$pid/review" -Headers @{ Authorization = "Bearer $admin" } -ContentType "application/json" `
  -Body '{"action":"approve"}' | Out-Null

Write-Host "== wallet topup stub =="
$top = Invoke-RestMethod -Method Post -Uri "$base/api/v1/me/wallet/topup" -Headers @{
  Authorization = "Bearer $tokenA"
  "Idempotency-Key" = [guid]::NewGuid().ToString()
} -ContentType "application/json" -Body '{"amount_cents":10000,"method":"wechat"}'
$wallet = Invoke-RestMethod -Method Get -Uri "$base/api/v1/me/wallet" -Headers @{ Authorization = "Bearer $tokenA" }
Write-Host ("wallet_balance=" + $wallet.data.balance_cents)
if ($wallet.data.balance_cents -lt 10000) { throw "expected topup credited" }

Write-Host "== admin user lookup =="
$users = Invoke-RestMethod -Method Get -Uri "$base/admin/v1/users?q=$phoneA&limit=5" -Headers @{ Authorization = "Bearer $admin" }
if (-not $users.data.items -or $users.data.items.Count -lt 1) { throw "admin users should find phoneA" }

Write-Host "E2E_APP SMOKE OK activity=$aid post=$pid"
