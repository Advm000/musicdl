# ============================================================
#  RECUPERATION AUTOMATIQUE - TELEPHONE USB (MTP)
#  Samsung + Android  |  Sans debogage USB requis
# ============================================================

param(
    [string]$Destination = "$env:USERPROFILE\Desktop\RECUPERATION_$(Get-Date -Format 'yyyy-MM-dd_HH-mm')"
)

function Info($m)  { Write-Host "  $m" -ForegroundColor Cyan }
function OK($m)    { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Err($m)   { Write-Host "  [X]  $m" -ForegroundColor Red }
function Title($m) { Write-Host "`n$m" -ForegroundColor White }

Clear-Host
Write-Host "============================================" -ForegroundColor Magenta
Write-Host "   RECUPERATION DONNEES TELEPHONE USB       " -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta

Title "ETAPE 1 - Detection du telephone..."

$shell = New-Object -ComObject Shell.Application
$monPC = $shell.NameSpace(17)

$telephones = @()
foreach ($item in $monPC.Items()) {
    $type = $item.Type
    if ($type -match "portable|phone|appareil|device|Android|iPhone|Samsung|MTP|PTP") {
        $telephones += $item
    }
}

if ($telephones.Count -eq 0) {
    foreach ($item in $monPC.Items()) {
        $path = $item.Path
        if ($path -notmatch '^[A-Z]:\\' -and $path -notmatch '\\\\') {
            $telephones += $item
        }
    }
}

if ($telephones.Count -eq 0) {
    Err "Aucun telephone detecte !"
    Write-Host ""
    Warn "Verifiez :"
    Write-Host "   1. Cable USB bien branche"
    Write-Host "   2. Telephone allume"
    Write-Host "   3. Mode USB = Transfert de fichiers (MTP)"
    Write-Host "      Essayez : Volume Haut/Bas apres branchement"
    Write-Host ""
    Write-Host "Appuyez sur une touche pour quitter..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

foreach ($t in $telephones) {
    OK "Telephone detecte : $($t.Name)"
}

Title "ETAPE 2 - Creation du dossier de sauvegarde..."
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
OK "Sauvegarde dans : $Destination"

$totalFichiers = 0
$totalErreurs  = 0

function Copy-MTPItem {
    param($shellItem, $destPath)

    $nom = $shellItem.Name

    if ($shellItem.IsFolder) {
        $newDest = Join-Path $destPath $nom
        New-Item -ItemType Directory -Path $newDest -Force | Out-Null
        $sousDossier = $shellItem.GetFolder()
        foreach ($enfant in $sousDossier.Items()) {
            Copy-MTPItem -shellItem $enfant -destPath $newDest
        }
    }
    else {
        $cible = Join-Path $destPath $nom
        if (Test-Path $cible) { return }

        try {
            $destShell = $shell.NameSpace($destPath)
            $destShell.CopyHere($shellItem, 0x14)

            $attente = 0
            while (-not (Test-Path $cible) -and $attente -lt 30) {
                Start-Sleep -Milliseconds 500
                $attente++
            }

            if (Test-Path $cible) {
                $script:totalFichiers++
                Write-Host "    + $nom" -ForegroundColor DarkGreen
            }
            else {
                $script:totalErreurs++
                Warn "Timeout : $nom"
            }
        }
        catch {
            $script:totalErreurs++
            Warn "Erreur : $nom"
        }
    }
}

$priorites = @(
    "DCIM", "Pictures", "WhatsApp", "Telegram",
    "Downloads", "Documents", "Music", "Videos",
    "Snapchat", "Instagram", "Contacts", "Backup", "Android"
)

foreach ($telephone in $telephones) {
    Title "ETAPE 3 - Recuperation de : $($telephone.Name)"

    $dossierTel = $telephone.GetFolder()
    $destTel = Join-Path $Destination ($telephone.Name -replace '[\\/:*?"<>|]', '_')
    New-Item -ItemType Directory -Path $destTel -Force | Out-Null

    $listeRacine = @{}
    foreach ($item in $dossierTel.Items()) {
        $listeRacine[$item.Name.ToUpper()] = $item
    }

    foreach ($prio in $priorites) {
        if ($listeRacine.ContainsKey($prio.ToUpper())) {
            Info "Copie de $prio..."
            Copy-MTPItem -shellItem $listeRacine[$prio.ToUpper()] -destPath $destTel
        }
    }

    foreach ($item in $dossierTel.Items()) {
        $dejaCopie = $false
        foreach ($p in $priorites) {
            if ($p.ToUpper() -eq $item.Name.ToUpper()) {
                $dejaCopie = $true
                break
            }
        }
        if (-not $dejaCopie) {
            Info "Copie de $($item.Name)..."
            Copy-MTPItem -shellItem $item -destPath $destTel
        }
    }
}

Title "============================================"
Write-Host "   RECUPERATION TERMINEE !" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
OK "$totalFichiers fichiers recuperes"
if ($totalErreurs -gt 0) {
    Warn "$totalErreurs fichiers non accessibles (normal pour fichiers systeme)"
}
OK "Dossier : $Destination"
Write-Host ""

Start-Process explorer.exe $Destination
