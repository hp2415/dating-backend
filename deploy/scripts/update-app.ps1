# Rebuild API / worker / admin / nginx only.
param(
    [string]$EnvFile = ""
)

$DeployDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Split-Path -Parent $DeployDir

if (-not $EnvFile) {
    $EnvFile = Join-Path $BackendDir ".env"
}
if (-not (Test-Path $EnvFile)) {
    throw "Missing $EnvFile"
}
$EnvFile = ((Resolve-Path $EnvFile).Path -replace "\\", "/")

$env:ENV_FILE = $EnvFile
docker compose -p dating-app `
    -f (Join-Path $DeployDir "compose.app.yml") `
    -f (Join-Path $DeployDir "compose.app.local.yml") `
    --env-file $EnvFile `
    up -d --build

if ($LASTEXITCODE -ne 0) { throw "app update failed" }
Write-Host "App stack updated. Infra was not restarted."
