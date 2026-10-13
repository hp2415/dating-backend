# Profile extras + follow graph smoke:
# login A/B -> legacy profile PUT keeps working -> extras write/clear -> follow/unfollow -> lists and counts
$ErrorActionPreference = "Stop"
$base = if ($env:SMOKE_BASE) { $env:SMOKE_BASE } else { "http://localhost:8000" }

function Login([string]$phone) {
  try {
    $body = '{"phone":"' + $phone + '"}'
    Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/send" -ContentType "application/json" -Body $body | Out-Null
  } catch {
    # Dev login accepts fixed code even if send is rate-limited
  }
  $body = '{"phone":"' + $phone + '","code":"123456","device_id":"profile-social-smoke","platform":"android"}'
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/sms/login" -ContentType "application/json" -Body $body
  return $login.data.tokens.access_token
}

function Api([string]$method, [string]$path, [string]$token, [string]$body = $null) {
  $req = @{ Method = $method; Uri = "$base$path"; Headers = @{ Authorization = "Bearer $token" } }
  if ($body) {
    $req.ContentType = "application/json; charset=utf-8"
    $req.Body = [System.Text.Encoding]::UTF8.GetBytes($body)
  }
  $res = Invoke-RestMethod @req
  if ($res.code -ne 0) { throw "$method $path failed: code=$($res.code) $($res.message)" }
  return $res.data
}

$suffix = Get-Date -Format "HHmmss"
$tokenA = Login ("136" + $suffix.PadLeft(8, "0"))
$tokenB = Login ("137" + $suffix.PadLeft(8, "0"))

Write-Host "== legacy profile PUT (no extras) =="
Api Put "/api/v1/me/profile" $tokenA '{"display_name":"SocialA","birthday":"1998-05-05","gender":"female","city":"Shanghai","bio":"smoke","tags":["travel"]}' | Out-Null
$meB = Api Put "/api/v1/me/profile" $tokenB '{"display_name":"SocialB","birthday":"1997-07-07","gender":"male","city":"Shanghai"}'
$idB = $meB.id
$meA = Api Get "/api/v1/me" $tokenA
$idA = $meA.id
if ($meA.profile.display_name -ne "SocialA") { throw "legacy display_name lost" }
if ($null -ne $meA.profile.mbti) { throw "mbti should default to null" }

Write-Host "== write extras =="
# zodiac = 狮子座 (escaped to stay ASCII-safe in Windows PowerShell)
$me = Api Put "/api/v1/me/profile" $tokenA '{"height_cm":168,"weight_kg":52,"occupation":"\u4e0a\u73ed","meet_radius":"\u540c\u57ce\u89c1\u9762","mbti":"ENFP","zodiac":"\u72ee\u5b50\u5ea7"}'
if ($me.profile.mbti -ne "ENFP" -or $me.profile.height_cm -ne 168) { throw "extras not saved" }
if ($me.profile.display_name -ne "SocialA") { throw "extras PUT clobbered display_name" }

Write-Host "== null on legacy field is ignored, null on extra clears =="
$me = Api Put "/api/v1/me/profile" $tokenA '{"display_name":null,"mbti":null}'
if ($me.profile.display_name -ne "SocialA") { throw "null display_name must be ignored" }
if ($null -ne $me.profile.mbti) { throw "null mbti should clear" }
if ($me.profile.height_cm -ne 168) { throw "omitted height_cm should stay" }

Write-Host "== invalid mbti rejected =="
$rejected = $false
try { Api Put "/api/v1/me/profile" $tokenA '{"mbti":"XXXX"}' | Out-Null } catch { $rejected = $true }
if (-not $rejected) { throw "invalid mbti accepted" }

Write-Host "== follow =="
$f = Api Post "/api/v1/users/$idB/follow" $tokenA
if (-not $f.is_following -or $f.followers_count -ne 1) { throw "follow failed" }
$f = Api Post "/api/v1/users/$idB/follow" $tokenA
if ($f.followers_count -ne 1) { throw "follow not idempotent" }

$selfRejected = $false
try { Api Post "/api/v1/users/$idA/follow" $tokenA | Out-Null } catch { $selfRejected = $true }
if (-not $selfRejected) { throw "self follow accepted" }

$pub = Api Get "/api/v1/users/$idB" $tokenA
if (-not $pub.is_following -or $pub.followers_count -ne 1) { throw "public profile follow stats wrong" }

$following = Api Get "/api/v1/me/following" $tokenA
if ($following.page_info.total -ne 1 -or $following.items[0].id -ne $idB) { throw "following list wrong" }
$followers = Api Get "/api/v1/me/followers" $tokenB
if ($followers.page_info.total -ne 1 -or $followers.items[0].is_mutual) { throw "followers list wrong" }

Write-Host "== mutual =="
Api Post "/api/v1/users/$idA/follow" $tokenB | Out-Null
$followers = Api Get "/api/v1/me/followers" $tokenB
if (-not $followers.items[0].is_mutual) { throw "expected mutual" }

Write-Host "== unfollow =="
$u = Api Delete "/api/v1/users/$idB/follow" $tokenA
if ($u.is_following -or $u.followers_count -ne 0) { throw "unfollow failed" }
$following = Api Get "/api/v1/me/following" $tokenA
if ($following.page_info.total -ne 0) { throw "following not cleared" }

Write-Host "PROFILE SOCIAL SMOKE OK"
