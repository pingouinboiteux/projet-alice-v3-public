param([string]$GameDirectory)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'steam_paths.ps1')
if (-not $GameDirectory) { $GameDirectory = Find-SlaySpireDirectory }
$GameDirectory = (Resolve-Path -LiteralPath $GameDirectory).Path
$cache = Join-Path $PSScriptRoot '..\..\data\cache\slay_spire'
$steamcmd = Join-Path $PSScriptRoot '..\..\data\cache\steamcmd'
$backup = Join-Path $PSScriptRoot '..\..\data\sauvegardes\validation_sts_mods_20261111'
New-Item -ItemType Directory -Force -Path $cache, $steamcmd, $backup | Out-Null

$zip = Join-Path $steamcmd 'steamcmd.zip'
$exe = Join-Path $steamcmd 'steamcmd.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    if (-not (Test-Path -LiteralPath $zip)) {
        Invoke-WebRequest -UseBasicParsing 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip' -OutFile $zip
    }
    Expand-Archive -LiteralPath $zip -DestinationPath $steamcmd -Force
}
if (-not (Test-Path -LiteralPath $exe)) { throw 'SteamCMD introuvable.' }

$items = @(
    @{ Id = '1605060445'; Name = 'ModTheSpire.jar'; Hash = '541B5E8A875D2A404A5A6D54F4A6F814284B0CF71ACB9245239D9C5EF50EA604' },
    @{ Id = '1605833019'; Name = 'BaseMod.jar'; Hash = 'C3353C10E64C621B723E9FD7D0502DFA796F828B101B68513594A5F5EF83FBAF' }
)
foreach ($item in $items) {
    $source = Join-Path $steamcmd ('steamapps\workshop\content\646570\' + $item.Id + '\' + $item.Name)
    if (-not (Test-Path -LiteralPath $source)) {
        & $exe +login anonymous +workshop_download_item 646570 $item.Id +quit
    }
    if (-not (Test-Path -LiteralPath $source)) { throw ('Steam Workshop ne fournit pas ' + $item.Name) }
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $item.Hash) {
        throw ('Version Workshop modifiee : examiner ' + $item.Name + ' avant installation.')
    }
}

$communication = Join-Path $cache 'CommunicationMod.jar'
if (-not (Test-Path -LiteralPath $communication)) {
    Invoke-WebRequest -UseBasicParsing 'https://github.com/ForgottenArbiter/CommunicationMod/releases/download/v1.2.1/CommunicationMod.jar' -OutFile $communication
}
if ((Get-FileHash -LiteralPath $communication -Algorithm SHA256).Hash -ne
    '12B99249ECCFD5245DDB0B6B7575E1A1DFBA0CE0ED6FAD5BD5BBD4A303897EF5') {
    throw 'Empreinte inattendue pour CommunicationMod.jar.'
}

$mods = Join-Path $GameDirectory 'mods'
New-Item -ItemType Directory -Force -Path $mods | Out-Null
$targets = @(
    @{ Source = (Join-Path $steamcmd 'steamapps\workshop\content\646570\1605060445\ModTheSpire.jar'); Target = (Join-Path $GameDirectory 'ModTheSpire.jar'); OldHash = '3112303BF4BC864586EF4406D28D485F2D40530AE7033A807A93AB7BAD0FC7B8' },
    @{ Source = (Join-Path $steamcmd 'steamapps\workshop\content\646570\1605833019\BaseMod.jar'); Target = (Join-Path $mods 'BaseMod.jar'); OldHash = '81B6B39322497962DFBAB39D938AC119A62A7F14239DD52A0722CEFAFE08B2E2' },
    @{ Source = $communication; Target = (Join-Path $mods 'CommunicationMod.jar'); OldHash = '' }
)
foreach ($item in $targets) {
    $expected = (Get-FileHash -LiteralPath $item.Source -Algorithm SHA256).Hash
    if (Test-Path -LiteralPath $item.Target) {
        $installed = (Get-FileHash -LiteralPath $item.Target -Algorithm SHA256).Hash
        if ($installed -eq $expected) { continue }
        if ($installed -ne $item.OldHash) { throw ('Mod inconnu deja present : ' + $item.Target) }
        Copy-Item -LiteralPath $item.Target -Destination (Join-Path $backup ([IO.Path]::GetFileName($item.Target)))
    }
    Copy-Item -LiteralPath $item.Source -Destination $item.Target -Force
}

$python = (& python -c 'import sys; print(sys.executable)').Trim()
if (-not (Test-Path -LiteralPath $python)) { throw 'Python introuvable.' }
$agent = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'agent.py')).Path
if ($python.Contains(' ') -or $agent.Contains(' ')) {
    throw 'Les chemins de Python et du projet Alice doivent etre sans espace pour CommunicationMod.'
}
$command = ($python + ' ' + $agent).Replace('\', '\\').Replace(':', '\:')
$configDir = Join-Path $env:LOCALAPPDATA 'ModTheSpire\CommunicationMod'
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$config = Join-Path $configDir 'config.properties'
$contents = "command=$command`nrunAtGameStart=true`n"
if (Test-Path -LiteralPath $config) {
    $existing = Get-Content -LiteralPath $config -Raw
    if ($existing -ne $contents) { throw ('Configuration deja presente : ' + $config) }
} else {
    [IO.File]::WriteAllText($config, $contents, [Text.Encoding]::ASCII)
}
Write-Output ('Mods installes dans : ' + $GameDirectory)
Write-Output ('Configuration : ' + $config)
