# ==============================================================================
# NO-CAP (SIH26188) — Owner Environment Isolation Audit Script (Task P13)
# ==============================================================================
# Run by the OWNER to verify secret isolation between production and test projects.
# PRINTS ONLY: "NAME: SAME|DIFFERENT|MISSING" — NEVER prints raw secret values.
# Temporary files are securely purged upon completion.
# ==============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$ProductionProject = "",

    [Parameter(Mandatory=$false)]
    [string]$TestProject = ""
)

$ErrorActionPreference = "Stop"

# Target variables to audit for isolation
$TargetVars = @(
    "DATABASE_URL",
    "MASTER_VAULT_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "ML_SERVICE_SECRET",
    "ML_SECRET_KEY",
    "HF_TOKEN"
)

function Get-Sha256Prefix8([string]$val) {
    if ([string]::IsNullOrEmpty($val)) { return $null }
    $cleanVal = $val.Trim()
    if ($cleanVal.Length -eq 0) { return $null }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($cleanVal)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    $hash = $hasher.ComputeHash($bytes)
    $hex = -join ($hash | ForEach-Object { "{0:x2}" -f $_ })
    return $hex.Substring(0, 8)
}

function Parse-EnvFile([string]$filePath) {
    $dict = @{}
    if (-not (Test-Path $filePath)) { return $dict }
    Get-Content $filePath | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -gt 0 -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim().Trim('"').Trim("'")
            $dict[$k] = $v
        }
    }
    return $dict
}

# Verify Vercel CLI availability
$vercelCmd = Get-Command "vercel" -ErrorAction SilentlyContinue
if (-not $vercelCmd) {
    Write-Host "Vercel CLI not found in PATH. Install with: npm i -g vercel"
    exit 1
}

if ([string]::IsNullOrEmpty($ProductionProject)) {
    $ProductionProject = Read-Host "Enter production Vercel project name or ID"
}
if ([string]::IsNullOrEmpty($TestProject)) {
    $TestProject = Read-Host "Enter test/staging Vercel project name or ID"
}

$tempProd = [System.IO.Path]::GetTempFileName()
$tempTest = [System.IO.Path]::GetTempFileName()

try {
    Write-Host "Pulling environment variables into temporary files..."
    & vercel env pull $tempProd --environment production --project $ProductionProject --yes | Out-Null
    & vercel env pull $tempTest --environment production --project $TestProject --yes | Out-Null

    $prodEnv = Parse-EnvFile $tempProd
    $testEnv = Parse-EnvFile $tempTest

    Write-Host "=== Isolation Audit Results ==="
    foreach ($varName in $TargetVars) {
        $prodVal = $prodEnv[$varName]
        $testVal = $testEnv[$varName]

        $prodHash = Get-Sha256Prefix8 $prodVal
        $testHash = Get-Sha256Prefix8 $testVal

        if ([string]::IsNullOrEmpty($prodHash) -or [string]::IsNullOrEmpty($testHash)) {
            Write-Host "$($varName): MISSING"
        } elseif ($prodHash -eq $testHash) {
            Write-Host "$($varName): SAME"
        } else {
            Write-Host "$($varName): DIFFERENT"
        }
    }
} finally {
    # Purge temporary env files immediately
    if (Test-Path $tempProd) { Remove-Item -Path $tempProd -Force -ErrorAction SilentlyContinue }
    if (Test-Path $tempTest) { Remove-Item -Path $tempTest -Force -ErrorAction SilentlyContinue }
}
