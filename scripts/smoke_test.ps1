# Smoke test for M1 auth + profile (PowerShell)
# Usage: .\scripts\smoke_test.ps1

$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"

Write-Host "== health =="
Invoke-RestMethod "$base/health" | ConvertTo-Json -Depth 5

Write-Host "== sms send =="
$send = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/send" `
  -ContentType "application/json" `
  -Body '{"phone":"13800138000"}'
$send | ConvertTo-Json -Depth 5
$code = if ($send.data.dev_code) { $send.data.dev_code } else { "123456" }

Write-Host "== sms login =="
$login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/login" `
  -ContentType "application/json" `
  -Body (@{
    phone = "13800138000"
    code = $code
    device_id = "smoke-1"
    platform = "android"
  } | ConvertTo-Json)
$login | ConvertTo-Json -Depth 6
$token = $login.data.tokens.access_token

Write-Host "== update profile =="
$me = Invoke-RestMethod -Method Put -Uri "$base/api/v1/me/profile" `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body (@{
    display_name = "林夏"
    birthday = "1998-05-20"
    gender = "female"
    city = "上海"
    bio = "喜欢城市漫步"
    tags = @("旅行", "咖啡")
  } | ConvertTo-Json)
$me | ConvertTo-Json -Depth 6

Write-Host "== get me =="
Invoke-RestMethod -Method Get -Uri "$base/api/v1/me" `
  -Headers @{ Authorization = "Bearer $token" } | ConvertTo-Json -Depth 6

Write-Host "SMOKE OK"
