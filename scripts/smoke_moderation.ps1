# Moderation smoke: report -> admin resolve limit -> limited user blocked from discover
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"

function Login([string]$phone) {
  try {
    Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/send" -ContentType "application/json" -Body ('{"phone":"' + $phone + '"}') | Out-Null
  } catch {}
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/login" -ContentType "application/json" -Body ('{"phone":"' + $phone + '","code":"123456","device_id":"mod-smoke","platform":"android"}')
  return $login.data.tokens.access_token
}

function PutProfile([string]$token, [string]$name, [string]$gender) {
  $body = '{"display_name":"' + $name + '","birthday":"1999-01-01","gender":"' + $gender + '","city":"Shanghai","bio":"mod smoke","tags":["travel"]}'
  Invoke-RestMethod -Method Put -Uri "$base/api/v1/me/profile" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body | Out-Null
}

$suffix = Get-Date -Format "HHmmss"
$phoneA = "137" + $suffix.PadLeft(8, "0")
$phoneB = "136" + $suffix.PadLeft(8, "0")

Write-Host "== login A/B =="
$tokenA = Login $phoneA
PutProfile $tokenA "ReporterA" "female"
$tokenB = Login $phoneB
PutProfile $tokenB "TargetB" "male"
$meB = Invoke-RestMethod -Method Get -Uri "$base/api/v1/me" -Headers @{ Authorization = "Bearer $tokenB" }
$idB = $meB.data.id
Write-Host "targetB=$idB"

Write-Host "== A reports B =="
$body = '{"target_user_id":"' + $idB + '","reason":"harassment","detail":"smoke report","also_block":true}'
$rep = Invoke-RestMethod -Method Post -Uri "$base/api/v1/reports" -Headers @{ Authorization = "Bearer $tokenA" } -ContentType "application/json" -Body $body
Write-Host ("report_id=" + $rep.data.id + " blocked=" + $rep.data.blocked)

Write-Host "== A block list =="
$blocks = Invoke-RestMethod -Method Get -Uri "$base/api/v1/blocks" -Headers @{ Authorization = "Bearer $tokenA" }
Write-Host ("block_count=" + $blocks.data.items.Count)
if ($blocks.data.items.Count -lt 1) { throw "expected block list" }

Write-Host "== admin login =="
$admin = Invoke-RestMethod -Method Post -Uri "$base/admin/v1/auth/login" -ContentType "application/json" -Body '{"username":"admin","password":"Admin@123456"}'
$adminToken = $admin.data.access_token

Write-Host "== admin reports pending =="
$reports = Invoke-RestMethod -Method Get -Uri "$base/admin/v1/reports?status=pending" -Headers @{ Authorization = "Bearer $adminToken" }
$found = @($reports.data.items | Where-Object { $_.id -eq $rep.data.id })
if ($found.Count -lt 1) { throw "report not in admin queue" }
Write-Host ("pending_total=" + $reports.data.total)

Write-Host "== admin resolve limit =="
$body = '{"resolution":"limit","admin_note":"smoke limit"}'
$resolved = Invoke-RestMethod -Method Post -Uri ("$base/admin/v1/reports/" + $rep.data.id + "/resolve") -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $body
Write-Host ("status=" + $resolved.data.status + " resolution=" + $resolved.data.resolution)

Write-Host "== B discover should be forbidden =="
try {
  Invoke-RestMethod -Method Get -Uri "$base/api/v1/discover/cards?limit=5" -Headers @{ Authorization = "Bearer $tokenB" } | Out-Null
  throw "expected limited user to fail discover"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 403) {
    # Invoke-RestMethod may surface differently; parse message if present
    $msg = $_.ErrorDetails.Message
    if ($msg -notmatch "50006|受限|403") { throw $_ }
  }
  Write-Host "limited_ok"
}

Write-Host "== seed pending media via SQL =="
docker exec dating-postgres psql -U dating -d dating -c "UPDATE media_assets SET audit_status='pending' WHERE id IN (SELECT id FROM media_assets LIMIT 1);" | Out-Null
$media = Invoke-RestMethod -Method Get -Uri "$base/admin/v1/media?audit_status=pending" -Headers @{ Authorization = "Bearer $adminToken" }
Write-Host ("pending_media=" + $media.data.total)
if ($media.data.total -lt 1) { throw "expected pending media" }
$mid = $media.data.items[0].id
$reviewed = Invoke-RestMethod -Method Post -Uri "$base/admin/v1/media/$mid/review" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body '{"action":"approve"}'
Write-Host ("media_status=" + $reviewed.data.audit_status)

Write-Host "== dashboard metrics =="
$dash = Invoke-RestMethod -Method Get -Uri "$base/admin/v1/dashboard/summary" -Headers @{ Authorization = "Bearer $adminToken" }
Write-Host ("users_total=" + $dash.data.metrics.users_total + " reports_pending=" + $dash.data.metrics.reports_pending)

Write-Host "MODERATION SMOKE OK"
