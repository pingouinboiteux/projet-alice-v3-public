# Reinstall the pinned, private code runner without changing Alice's active model.
$ErrorActionPreference = 'Stop'
$labRoot = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $labRoot 'runtime/codex-mxc'
$package = Join-Path $destination 'node_modules/@openai/codex/package.json'
if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    throw 'Node.js is required for the isolated code workshop.'
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'npm is required for the isolated code workshop.'
}
& npm.cmd install --prefix $destination '@openai/codex@0.167.0' --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Codex installation failed.' }
if (-not (Test-Path -LiteralPath $package)) { throw 'Codex package is missing.' }
$version = (Get-Content -LiteralPath $package -Raw | ConvertFrom-Json).version
if ($version -ne '0.167.0') { throw 'Unexpected Codex version.' }
Write-Output 'Codex 0.167.0 installed in the laboratory runtime.'
