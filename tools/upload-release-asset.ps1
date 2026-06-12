# Upload robuste d'un asset de release GitHub (HTTP/1.1, retries, verification d'etat)
# Usage: .\tools\upload-release-asset.ps1 -ReleaseId 338188432 -File dist\Music-DL-Setup.exe -Name Music-DL-Setup.exe
param(
  [Parameter(Mandatory=$true)] [long]$ReleaseId,
  [Parameter(Mandatory=$true)] [string]$File,
  [Parameter(Mandatory=$true)] [string]$Name,
  [string]$Repo = 'Advm000/musicdl'
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$tok = (git remote get-url origin) -replace '.*:(ghp_[^@]+)@.*','$1'
$h = @{Authorization = "token $tok"; Accept = 'application/vnd.github+json'}

for ($try = 1; $try -le 3; $try++) {
  Write-Host "--- Tentative $try ---"
  # 1. Supprimer l'asset existant du meme nom (casse ou partiel)
  $assets = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/$ReleaseId/assets" -Headers $h
  $old = $assets | Where-Object { $_.name -eq $Name }
  if ($old) {
    Invoke-RestMethod -Method Delete -Uri "https://api.github.com/repos/$Repo/releases/assets/$($old.id)" -Headers $h | Out-Null
    Write-Host "Ancien asset supprime (state=$($old.state))"
    Start-Sleep 3
  }
  # 2. Upload en HTTP/1.1 (curl en processus enfant + sortie periodique anti-timeout)
  $curlArgs = "--http1.1 -sS -X POST -H ""Authorization: token $tok"" -H ""Content-Type: application/octet-stream"" --data-binary ""@$File"" --max-time 1500 ""https://uploads.github.com/repos/$Repo/releases/$ReleaseId/assets?name=$Name"" -o ""$env:TEMP\gh-upload-out.json"" -w ""curl: HTTP %{http_code} en %{time_total}s"""
  $p = Start-Process -FilePath "$env:SystemRoot\System32\curl.exe" -ArgumentList $curlArgs -NoNewWindow -PassThru
  $t0 = Get-Date
  while (-not $p.HasExited) {
    Start-Sleep 15
    Write-Host ("upload en cours... {0}s" -f [int]((Get-Date) - $t0).TotalSeconds)
  }
  Write-Host "curl exit code: $($p.ExitCode)"
  # 3. Verifier l'etat final cote API (la finalisation GitHub peut prendre du temps)
  for ($w = 1; $w -le 12; $w++) {
    Start-Sleep 15
    $assets = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/$ReleaseId/assets" -Headers $h
    $a = $assets | Where-Object { $_.name -eq $Name }
    $st = 'absent'; if ($a) { $st = $a.state }
    Write-Host "verif $w : state=$st"
    if ($st -eq 'uploaded') {
      Write-Host "SUCCES: $Name state=uploaded, $([math]::Round($a.size/1MB,1)) MB"
      exit 0
    }
  }
  Write-Host "Etat apres tentative: pas finalise - on reessaie"
}
Write-Host "ECHEC apres 3 tentatives"
exit 1
