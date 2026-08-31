# First-time start on Windows. Always uses local port mappings.
#   .\deploy\scripts\first-up.ps1
#   .\deploy\scripts\first-up.ps1 -ReuseInfra -Postgres dating-postgres -Redis dating-redis
param(
    [switch]$ReuseInfra,
    [switch]$Minio,
    [string]$EnvFile = "",
    [string]$Postgres = "dating-postgres",
    [string]$Redis = "dating-redis"
)

$DeployDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Split-Path -Parent $DeployDir

if (-not $EnvFile) {
    $EnvFile = Join-Path $BackendDir ".env"
}
if (-not (Test-Path $EnvFile)) {
    throw "Missing $EnvFile . Run: copy .env.example .env"
}
$EnvFile = ((Resolve-Path $EnvFile).Path -replace "\\", "/")

$env:ENV_FILE = $EnvFile

function Ensure-Network {
    docker network inspect dating-net 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        docker network create dating-net
    }
}

function Wait-Healthy([string]$Name) {
    for ($i = 0; $i -lt 60; $i++) {
        $running = docker inspect --format "{{.State.Running}}" $Name 2>$null
        $health = docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" $Name 2>$null
        if ($running -eq "true" -and ($health -eq "healthy" -or $health -eq "none")) {
            Write-Host "$Name is ready ($health)"
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Timeout waiting for $Name"
}

Ensure-Network

$infra = @(
    "compose", "-p", "dating-infra",
    "-f", (Join-Path $DeployDir "compose.infra.yml"),
    "-f", (Join-Path $DeployDir "compose.infra.local.yml"),
    "--env-file", $EnvFile
)
$app = @(
    "compose", "-p", "dating-app",
    "-f", (Join-Path $DeployDir "compose.app.yml"),
    "-f", (Join-Path $DeployDir "compose.app.local.yml"),
    "--env-file", $EnvFile
)

if ($ReuseInfra) {
    Write-Host "Reusing $Postgres / $Redis"
    docker network connect dating-net $Postgres 2>$null
    docker network connect dating-net $Redis 2>$null
} else {
    docker @infra up -d postgres redis
    if ($LASTEXITCODE -ne 0) { throw "infra up failed" }
    Wait-Healthy dating-postgres
    Wait-Healthy dating-redis
}

if ($Minio) {
    Write-Host "Starting MinIO"
    docker @infra --profile minio up -d minio minio-init
} else {
    Write-Host "Skipping MinIO. Point OSS_* at Aliyun OSS."
}

docker @app up -d --build
if ($LASTEXITCODE -ne 0) { throw "app up failed" }
Wait-Healthy dating-api
Wait-Healthy dating-nginx

Write-Host "Ready: API http://127.0.0.1:8000/docs   Admin http://127.0.0.1:8080/"
Write-Host "Stop the all-in-one compose first if container names already exist."
