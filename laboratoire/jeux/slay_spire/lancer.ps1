param([string]$GameDirectory, [ValidateSet('policy', 'alice')][string]$Mode = 'alice')

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'steam_paths.ps1')
if (-not $GameDirectory) { $GameDirectory = Find-SlaySpireDirectory }
$GameDirectory = (Resolve-Path -LiteralPath $GameDirectory).Path
$slots = Join-Path $GameDirectory 'preferences\STSSaveSlots'
if (-not (Test-Path -LiteralPath $slots)) {
    throw 'Impossible de verifier le profil actif du jeu.'
}
$profile = Get-Content -LiteralPath $slots -Raw | ConvertFrom-Json
if ([string]$profile.'1_PROFILE_NAME' -ne 'validationAlice') {
    throw 'Le profil de jeu reserve a Alice est introuvable.'
}
$runningGame = Get-Process -Name java, javaw, SlayTheSpire -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($GameDirectory, [StringComparison]::OrdinalIgnoreCase) }
if ($runningGame) { throw 'Fermer Slay the Spire avant de lancer Alice.' }
$java = Join-Path $GameDirectory 'jre\bin\java.exe'
$loader = Join-Path $GameDirectory 'ModTheSpire.jar'
if (-not (Test-Path -LiteralPath $java) -or -not (Test-Path -LiteralPath $loader)) {
    throw 'Jeu ou mods incomplets : lancer installer.ps1.'
}
$lab = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $lab '.venv_memory\Scripts\python.exe'
$pythonw = Join-Path $lab '.venv_memory\Scripts\pythonw.exe'
$desktop = Join-Path $lab 'scripts\alice_desktop.py'
$bridgeScript = Join-Path $lab 'scripts\game_stream_bridge.py'
$bridgeFile = Join-Path $lab 'data\slay_spire\bridge\current.json'
if ($Mode -eq 'alice') {
    if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $pythonw)) {
        throw 'Alice est incomplete : environnement Python du laboratoire introuvable.'
    }
    $oldPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $lab 'scripts'
        $otherGames = & $python -B -c "from chat import GAMES, processes; print(','.join(sorted(GAMES & processes())))"
    } finally {
        $env:PYTHONPATH = $oldPythonPath
    }
    if ($LASTEXITCODE -ne 0) { throw 'Controle des autres jeux indisponible.' }
    if ($otherGames) { throw ('Ferme les autres jeux avant de lancer Alice : ' + $otherGames) }
    $activeModel = Get-Process -Name llama-server -ErrorAction SilentlyContinue
    $reuse = $false
    if ($activeModel -and (Test-Path -LiteralPath $bridgeFile)) {
        try {
            $bridgeState = Get-Content -LiteralPath $bridgeFile -Raw | ConvertFrom-Json
            $owner = Get-Process -Id ([int]$bridgeState.pid) -ErrorAction SilentlyContinue
            if ($owner -and $owner.ProcessName -eq 'pythonw' -and
                [string]$bridgeState.token -match '^[0-9a-f]{64}$') {
                $env:ALICE_STS_BRIDGE_FILE = $bridgeFile
                $env:ALICE_STS_BRIDGE_TOKEN = [string]$bridgeState.token
                & $python -B $bridgeScript ping 2>$null
                $reuse = $LASTEXITCODE -eq 0
            }
        } catch { $reuse = $false }
    }
    if ($activeModel -and -not $reuse) {
        throw 'Alice est deja ouverte sans liaison avec le jeu. Ferme-la, puis relance ce raccourci.'
    }
    if (-not $reuse) {
        $env:ALICE_STS_BRIDGE_FILE = $bridgeFile
        $env:ALICE_STS_BRIDGE_TOKEN = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        $argument = '-B "' + $desktop + '" --twitch --sts-stream'
        $aliceProcess = Start-Process -FilePath $pythonw -ArgumentList $argument `
            -WorkingDirectory $lab -WindowStyle Normal -PassThru
        $deadline = (Get-Date).AddSeconds(180)
        $ready = $false
        while ((Get-Date) -lt $deadline) {
            if (Test-Path -LiteralPath $bridgeFile) {
                try {
                    $bridgeState = Get-Content -LiteralPath $bridgeFile -Raw | ConvertFrom-Json
                    $owner = Get-Process -Id ([int]$bridgeState.pid) -ErrorAction SilentlyContinue
                    if ($owner -and $owner.ProcessName -eq 'pythonw' -and
                        [string]$bridgeState.token -eq $env:ALICE_STS_BRIDGE_TOKEN) {
                        & $python -B $bridgeScript ping 2>$null
                        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
                    }
                } catch { }
            }
            Start-Sleep -Milliseconds 300
        }
        if (-not $ready) {
            throw 'Alice n a pas termine son chargement. Consulte sa fenetre, puis ferme-la avant de reessayer.'
        }
    }
    Write-Host 'Alice et sa voix sont pretes. Ouverture de Slay the Spire.'
}
$originalSlot = [string]$profile.DEFAULT_SLOT
$switched = $originalSlot -ne '1'
$utf8 = New-Object System.Text.UTF8Encoding $false
if ($switched) {
    $profile.DEFAULT_SLOT = '1'
    [IO.File]::WriteAllText($slots, ($profile | ConvertTo-Json -Depth 10), $utf8)
}
Push-Location $GameDirectory
try {
    $env:ALICE_STS_MODE = $Mode
    & $java -jar $loader --mods basemod,CommunicationMod --skip-intro
    if ($LASTEXITCODE -ne 0) { throw ('ModTheSpire a quitte avec le code ' + $LASTEXITCODE) }
} finally {
    Pop-Location
    if ($Mode -eq 'alice') {
        try { & $python -B $bridgeScript finish 2>$null | Out-Null } catch { }
    }
    if ($switched -and (Test-Path -LiteralPath $slots)) {
        $current = Get-Content -LiteralPath $slots -Raw | ConvertFrom-Json
        if ([string]$current.DEFAULT_SLOT -eq '1' -and
            [string]$current.'1_PROFILE_NAME' -eq 'validationAlice') {
            $current.DEFAULT_SLOT = $originalSlot
            [IO.File]::WriteAllText($slots, ($current | ConvertTo-Json -Depth 10), $utf8)
        }
    }
}
