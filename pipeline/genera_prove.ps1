# Genera i campioni di voce UNO PER PROCESSO: se una voce manda in errore la scheda video,
# la successiva riparte da zero e non si perde il resto. Le voci gia' fatte vengono saltate.
# Uso (da PowerShell):  .\genera_prove.ps1 ivanhoe 00-prova-italiano 90 Nome_Voce1 Nome_Voce2 ...
param([string]$Libro, [string]$Capitolo, [int]$Parole, [Parameter(ValueFromRemainingArguments=$true)][string[]]$Voci)

$env:PYTHONIOENCODING = "utf-8"
$env:COQUI_TOS_AGREED = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
# La scheda (RTX 5050 con driver 577.13) dava errori CUDA saltuari. Con le operazioni eseguite in modo
# sincrono (CUDA_LAUNCH_BLOCKING=1) la diagnosi su 15 frasi e' passata senza errori: lo teniamo attivo.
$env:CUDA_LAUNCH_BLOCKING = "1"
$ErrorActionPreference = "Continue"
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $aqui "..\.venv-xtts\Scripts\python.exe"
$riuscite = @(); $fallite = @()

foreach ($v in $Voci) {
    Write-Output "=== $v"
    $ok = $false
    # Gli errori CUDA sono saltuari: ogni voce si riprova fino a 3 volte, ogni volta in un processo nuovo
    foreach ($tentativo in 1..3) {
        $out = & $py -W ignore (Join-Path $aqui "prova_voci.py") $Libro $Capitolo $Parole "xtts:it:$v" 2>&1
        $out | Where-Object { $_ -match "durata|salto|scheda a|AcceleratorError|CUDA error" } | Select-Object -First 2
        if ($LASTEXITCODE -eq 0) { $ok = $true; break }
        Write-Output "  tentativo $tentativo fallito"
        Start-Sleep -Seconds 10
    }
    if ($ok) { $riuscite += $v } else { $fallite += $v; Write-Output "  -> FALLITA dopo 3 tentativi" }
    Start-Sleep -Seconds 3
}
Write-Output ""
Write-Output ("Riuscite: " + $riuscite.Count + "   Fallite: " + $fallite.Count)
if ($fallite.Count) { Write-Output ("Voci fallite: " + ($fallite -join ", ")) }
