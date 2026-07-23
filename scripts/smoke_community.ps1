# Community smoke: create post -> admin approve -> like -> comment
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"

function Login([string]$phone) {
  try {
    Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/send" -ContentType "application/json" -Body ('{"phone":"' + $phone + '"}') | Out-Null
  } catch {}
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/login" -ContentType "application/json" -Body ('{"phone":"' + $phone + '","code":"123456","device_id":"community-smoke","platform":"android"}')
  return $login.data.tokens.access_token
}

function PutProfile([string]$token, [string]$name, [string]$gender) {
  $body = '{"display_name":"' + $name + '","birthday":"1999-01-01","gender":"' + $gender + '","city":"Shanghai","bio":"community","tags":["travel"]}'
  Invoke-RestMethod -Method Put -Uri "$base/api/v1/me/profile" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body | Out-Null
}

$suffix = Get-Date -Format "HHmmss"
$phone = "135" + $suffix.PadLeft(8, "0")

Write-Host "== login =="
$token = Login $phone
PutProfile $token "CommunityUser" "female"

Write-Host "== create post with image url placeholder =="
$body = '{"content":"hello community smoke","media":[{"type":"image","url":"https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=400"}]}'
$created = Invoke-RestMethod -Method Post -Uri "$base/api/v1/community/posts" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body
$postId = $created.data.id
Write-Host ("post_id=" + $postId + " status=" + $created.data.status)
if ($created.data.status -ne "pending") { throw "expected pending post" }

Write-Host "== feed empty before approve =="
$feed = Invoke-RestMethod -Method Get -Uri "$base/api/v1/community/posts" -Headers @{ Authorization = "Bearer $token" }
$visible = @($feed.data.items | Where-Object { $_.id -eq $postId })
if ($visible.Count -gt 0) { throw "pending post should not be in public feed" }

Write-Host "== admin approve =="
$admin = Invoke-RestMethod -Method Post -Uri "$base/admin/v1/auth/login" -ContentType "application/json" -Body '{"username":"admin","password":"Admin@123456"}'
$adminToken = $admin.data.access_token
$reviewed = Invoke-RestMethod -Method Post -Uri "$base/admin/v1/community/posts/$postId/review" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body '{"action":"approve"}'
Write-Host ("status=" + $reviewed.data.status)

Write-Host "== feed contains post =="
$feed2 = Invoke-RestMethod -Method Get -Uri "$base/api/v1/community/posts" -Headers @{ Authorization = "Bearer $token" }
$visible2 = @($feed2.data.items | Where-Object { $_.id -eq $postId })
if ($visible2.Count -lt 1) { throw "approved post missing from feed" }

Write-Host "== like =="
$like = Invoke-RestMethod -Method Post -Uri "$base/api/v1/community/posts/$postId/like" -Headers @{ Authorization = "Bearer $token" }
Write-Host ("liked=" + $like.data.liked + " count=" + $like.data.like_count)

Write-Host "== comment =="
$c = Invoke-RestMethod -Method Post -Uri "$base/api/v1/community/posts/$postId/comments" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body '{"content":"nice post"}'
Write-Host ("comment_id=" + $c.data.id)

Write-Host "== comments list =="
$clist = Invoke-RestMethod -Method Get -Uri "$base/api/v1/community/posts/$postId/comments" -Headers @{ Authorization = "Bearer $token" }
Write-Host ("comment_count=" + $clist.data.items.Count)

Write-Host "COMMUNITY SMOKE OK"
