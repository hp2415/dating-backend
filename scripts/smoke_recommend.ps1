# Recommend smoke: browse shelves + engagement + buddies match_score
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"

function Login([string]$phone) {
  try {
    Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/send" -ContentType "application/json" -Body ('{"phone":"' + $phone + '"}') | Out-Null
  } catch {}
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/login" -ContentType "application/json" -Body ('{"phone":"' + $phone + '","code":"123456","device_id":"recommend-smoke","platform":"android"}')
  return $login.data.tokens.access_token
}

function PutProfile([string]$token, [string]$name, [string]$gender, [string]$tagsJson) {
  $body = '{"display_name":"' + $name + '","birthday":"1999-01-01","gender":"' + $gender + '","city":"Shanghai","bio":"recommend","tags":' + $tagsJson + '}'
  Invoke-RestMethod -Method Put -Uri "$base/api/v1/me/profile" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body | Out-Null
}

$suffix = Get-Date -Format "HHmmss"
$phoneA = "135" + $suffix.PadLeft(8, "0")
$phoneB = "136" + $suffix.PadLeft(8, "0")

Write-Host "== login =="
$tokenA = Login $phoneA
PutProfile $tokenA "RecHost" "female" '["sport","travel"]'
$tokenB = Login $phoneB
PutProfile $tokenB "RecBuddy" "male" '["sport","music"]'

Write-Host "== ensure published activity =="
$body = '{"title":"sport night run","description":"evening buddy jogging near park for fitness lovers","category":"sport","city":"Shanghai","address":"Century Park","capacity":8,"media":[{"type":"image","url":"https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=400"}]}'
$created = Invoke-RestMethod -Method Post -Uri "$base/api/v1/activities" -Headers @{ Authorization = "Bearer $tokenA" } -ContentType "application/json" -Body $body
$aid = $created.data.id
$admin = Invoke-RestMethod -Method Post -Uri "$base/admin/v1/auth/login" -ContentType "application/json" -Body '{"username":"admin","password":"Admin@123456"}'
$adminToken = $admin.data.access_token
Invoke-RestMethod -Method Post -Uri "$base/admin/v1/activities/$aid/review" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body '{"action":"approve"}' | Out-Null

Write-Host "== browse =="
$browse = Invoke-RestMethod -Method Get -Uri "$base/api/v1/activities/browse" -Headers @{ Authorization = "Bearer $tokenB" }
if ($null -eq $browse.data.shelves) { throw "missing shelves" }
Write-Host ("shelves=" + $browse.data.shelves.Count + " featured=" + ($null -ne $browse.data.featured))
if ($browse.data.shelves.Count -lt 1) { throw "expected at least one shelf when activities exist" }

Write-Host "== engagement =="
$engBody = '{"activity_id":"' + $aid + '","event":"view"}'
$eng = Invoke-RestMethod -Method Post -Uri "$base/api/v1/engagement/activities" -Headers @{ Authorization = "Bearer $tokenB" } -ContentType "application/json" -Body $engBody
if (-not $eng.data.recorded) { throw "engagement not recorded" }

Write-Host "== buddies recommend =="
$buddies = Invoke-RestMethod -Method Get -Uri "$base/api/v1/buddies/recommend?limit=10" -Headers @{ Authorization = "Bearer $tokenB" }
$items = @($buddies.data.items)
Write-Host ("buddies=" + $items.Count)
$withScore = @($items | Where-Object { $_.PSObject.Properties.Name -contains "match_score" })
if ($items.Count -gt 0 -and $withScore.Count -eq 0) { throw "match_score missing" }
if ($items.Count -gt 1) {
  for ($i = 1; $i -lt $items.Count; $i++) {
    if ($items[$i].match_score -gt $items[$i - 1].match_score) { throw "buddies not sorted by match_score desc" }
  }
}

Write-Host "RECOMMEND SMOKE OK"
