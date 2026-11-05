param(
    [ValidateSet('Plan','Apply','Verify','Rollback')][string]$Mode = 'Plan',
    [string]$ValidationRoot = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$WorkRoot = $ProjectRoot
if ($ValidationRoot) {
    $WorkRoot = [IO.Path]::GetFullPath($ValidationRoot)
    $Allowed = Join-Path $ProjectRoot 'data\validation\validation_migration_'
    if (-not $WorkRoot.StartsWith($Allowed,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Validation root must be an isolated validation_migration_ directory'
    }
}
$Pairs = @(
    @('logs','data/logs'),
    @('cache','data/cache/application'),
    @('laboratoire/logs','laboratoire/data/logs'),
    @('laboratoire/cache','laboratoire/data/cache'),
    @('laboratoire/outputs','laboratoire/data/outputs'),
    @('laboratoire/rapports','laboratoire/data/validation/rapports-historiques')
)
$StatePath = Join-Path $WorkRoot 'data\validation\migration_20261105\state.json'
function SafePath([string]$Relative) {
    $Full = [IO.Path]::GetFullPath((Join-Path $WorkRoot $Relative))
    if (-not $Full.StartsWith($WorkRoot + '\',[StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes project: $Relative"
    }
    # No ancestor junction may redirect a move outside the checked workspace.
    $Parent = Split-Path -Parent $Full
    while ($Parent.Length -gt $WorkRoot.Length) {
        if (Test-Path -LiteralPath $Parent) {
            if ((Get-Item -LiteralPath $Parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Unexpected linked ancestor: $Parent"
            }
        }
        $Parent = Split-Path -Parent $Parent
    }
    return $Full
}
function CheckLink($Pair) {
    $Old = SafePath $Pair[0]; $New = SafePath $Pair[1]
    $Item = Get-Item -LiteralPath $Old -Force
    if ($Item.LinkType -ne 'Junction' -or [IO.Path]::GetFullPath([string]$Item.Target) -ne $New) {
        throw "Unexpected compatibility link: $Old"
    }
    if (-not (Test-Path -LiteralPath $New -PathType Container)) { throw "Missing target: $New" }
}
function SaveState([string]$Status) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $StatePath) -Force | Out-Null
    @{status=$Status; pairs=$Pairs; version=1} | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $StatePath -Encoding ASCII
}
if ($Mode -eq 'Plan') {
    foreach ($Pair in $Pairs) {
        [pscustomobject]@{source=$Pair[0]; target=$Pair[1];
            sourceExists=(Test-Path -LiteralPath (SafePath $Pair[0]));
            targetExists=(Test-Path -LiteralPath (SafePath $Pair[1]))}
    }
    return
}
if ($Mode -eq 'Verify') {
    foreach ($Pair in $Pairs) { CheckLink $Pair }
    Write-Output 'Verified 6 compatibility junctions and physical targets'
    return
}
if ($Mode -in @('Apply','Rollback')) {
    if (-not $ValidationRoot) {
        $Active = @(Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($ProjectRoot + '\',[StringComparison]::OrdinalIgnoreCase) -and
            $_.Name -match '^(pythonw?|llama-server|node|godot).*\.exe$'
        })
        if ($Active.Count) { throw 'An Alice process is running; migration refused' }
    }
}
if ($Mode -eq 'Apply') {
    if (Test-Path -LiteralPath $StatePath) { throw 'State exists; inspect or rollback before retrying' }
    foreach ($Pair in $Pairs) {
        $Old=SafePath $Pair[0]; $New=SafePath $Pair[1]
        if (-not (Test-Path -LiteralPath $Old -PathType Container)) { throw "Missing source: $Old" }
        if ((Get-Item -LiteralPath $Old -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Source already linked: $Old" }
        if (Test-Path -LiteralPath $New) { throw "Destination already exists: $New" }
    }
    SaveState 'applying'
    foreach ($Pair in $Pairs) {
        $Old=SafePath $Pair[0]; $New=SafePath $Pair[1]
        New-Item -ItemType Directory -Path (Split-Path -Parent $New) -Force | Out-Null
        Move-Item -LiteralPath $Old -Destination $New
        New-Item -ItemType Junction -Path $Old -Target $New | Out-Null
        CheckLink $Pair
    }
    SaveState 'applied'
    Write-Output 'Moved 6 directories; original paths point to the same files'
    return
}
if (-not (Test-Path -LiteralPath $StatePath)) { throw 'No migration state to rollback' }
for ($Index=$Pairs.Count-1; $Index -ge 0; $Index--) {
    $Pair=$Pairs[$Index];$Old=SafePath $Pair[0];$New=SafePath $Pair[1]
    if (Test-Path -LiteralPath $New) {
        if (Test-Path -LiteralPath $Old) {
            CheckLink $Pair
            # Non-recursive deletion of this verified junction only; never its target.
            [IO.Directory]::Delete($Old)
        }
        Move-Item -LiteralPath $New -Destination $Old
    }
}
SaveState 'rolled_back'
Write-Output 'Restored physical directories at their original paths'
