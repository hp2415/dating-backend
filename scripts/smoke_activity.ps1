# Activity smoke: create -> admin approve -> join -> like -> comment
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"

function Login([string]$phone) {
  try {
    Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/send" -ContentType "application/json" -Body ('{"phone":"' + $phone + '"}') | Out-Null
  } catch {}
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/login" -ContentType "application/json" -Body ('{"phone":"' + $phone + '","code":"123456","device_id":"activity-smoke","platform":"android"}')
  return $login.data.tokens.access_token
}

function PutProfile([string]$token, [string]$name, [string]$gender) {
  $body = '{"display_name":"' + $name + '","birthday":"1999-01-01","gender":"' + $gender + '","city":"Shanghai","bio":"buddy","tags":["sport"]}'
  Invoke-RestMethod -Method Put -Uri "$base/api/v1/me/profile" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body | Out-Null
}

$suffix = Get-Date -Format "HHmmss"
$phoneA = "134" + $suffix.PadLeft(8, "0")
$phoneB = "133" + $suffix.PadLeft(8, "0")

Write-Host "== login host/member =="
$tokenA = Login $phoneA
PutProfile $tokenA "HostA" "female"
$tokenB = Login $phoneB
PutProfile $tokenB "MemberB" "male"

Write-Host "== create activity =="
$body = '{"title":"weekend run","description":"easy pace buddy run","category":"sport","city":"Shanghai","address":"Xuhui Riverside","capacity":6,"media":[{"type":"image","url":"https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=400"}]}'
$created = Invoke-RestMethod -Method Post -Uri "$base/api/v1/activities" -Headers @{ Authorization = "Bearer $tokenA" } -ContentType "application/json" -Body $body
$aid = $created.data.id
Write-Host ("activity_id=" + $aid + " status=" + $created.data.status)
if ($created.data.status -ne "pending") { throw "expected pending" }

Write-Host "== feed empty before approve =="
$feed = Invoke-RestMethod -Method Get -Uri "$base/api/v1/activities" -Headers @{ Authorization = "Bearer $tokenB" }
$hit = @($feed.data.items | Where-Object { $_.id -eq $aid })
if ($hit.Count -gt 0) { throw "pending activity should not be public" }

Write-Host "== admin approve =="
$admin = Invoke-RestMethod -Method Post -Uri "$base/admin/v1/auth/login" -ContentType "application/json" -Body '{"username":"admin","password":"Admin@123456"}'
$adminToken = $admin.data.access_token
$reviewed = Invoke-RestMethod -Method Post -Uri "$base/admin/v1/activities/$aid/review" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body '{"action":"approve"}'
Write-Host ("status=" + $reviewed.data.status)

Write-Host "== B joins =="
$join = Invoke-RestMethod -Method Post -Uri "$base/api/v1/activities/$aid/join" -Headers @{ Authorization = "Bearer $tokenB" }
Write-Host ("joined=" + $join.data.joined + " count=" + $join.data.join_count)

Write-Host "== detail =="
$detail = Invoke-RestMethod -Method Get -Uri "$base/api/v1/activities/$aid" -Headers @{ Authorization = "Bearer $tokenB" }
Write-Host ("members=" + $detail.data.members.Count + " address=" + $detail.data.address)

Write-Host "== like + comment dynamic =="
$like = Invoke-RestMethod -Method Post -Uri "$base/api/v1/activities/$aid/like" -Headers @{ Authorization = "Bearer $tokenB" }
$c = Invoke-RestMethod -Method Post -Uri "$base/api/v1/activities/$aid/comments" -Headers @{ Authorization = "Bearer $tokenB" } -ContentType "application/json" -Body '{"content":"see you there"}'
Write-Host ("liked=" + $like.data.liked + " comment=" + $c.data.id)

Write-Host "ACTIVITY SMOKE OK"
