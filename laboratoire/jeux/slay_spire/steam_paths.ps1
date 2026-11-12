function Find-SlaySpireDirectory {
    $steamKey = 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam'
    $steamRoot = (Get-ItemProperty -Path $steamKey -ErrorAction Stop).InstallPath
    $roots = @($steamRoot)
    $vdf = Join-Path $steamRoot 'steamapps\libraryfolders.vdf'
    if (Test-Path -LiteralPath $vdf) {
        foreach ($line in Get-Content -LiteralPath $vdf) {
            if ($line -match '"path"\s+"([^"]+)"') {
                $roots += $Matches[1].Replace('\\', '\')
            }
        }
    }
    foreach ($root in ($roots | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $manifest = Join-Path $root 'steamapps\appmanifest_646570.acf'
        $game = Join-Path $root 'steamapps\common\SlayTheSpire'
        if ((Test-Path -LiteralPath $manifest) -and
            (Test-Path -LiteralPath (Join-Path $game 'desktop-1.0.jar'))) {
            return $game
        }
    }
    throw 'Slay the Spire 1 introuvable dans les bibliotheques Steam installees.'
}
