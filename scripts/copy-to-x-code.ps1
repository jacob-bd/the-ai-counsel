<#
.SYNOPSIS
Clone or update The AI Counsel Electron wrapper branch under X:\Code for local testing.

.DESCRIPTION
This script creates a clean local test checkout from GitHub. By default it uses the
Electron wrapper branch and clones into:

    X:\Code\the-ai-counsel-electron-test

It is intentionally conservative:
- It will not delete an existing non-git folder unless -BackupExisting is supplied.
- It will not hard-reset an existing git checkout unless -ForceReset is supplied.
- It prints the exact follow-up commands for installing and starting the desktop app.

.EXAMPLE
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\copy-to-x-code.ps1

.EXAMPLE
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\copy-to-x-code.ps1 -ForceReset

.EXAMPLE
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\copy-to-x-code.ps1 -DestinationName the-ai-counsel
#>

[CmdletBinding()]
param(
    [string]$TargetRoot = 'X:\Code',
    [string]$DestinationName = 'the-ai-counsel-electron-test',
    [string]$RepoUrl = 'https://github.com/insane66613/the-ai-counsel.git',
    [string]$Branch = 'port-electron-wrapper',
    [switch]$ForceReset,
    [switch]$BackupExisting,
    [switch]$InstallDependencies,
    [switch]$StartDesktop
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found on PATH: $Name"
    }
}

function Invoke-Git {
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$WorkingDirectory = $null
    )

    $display = "git $($Arguments -join ' ')"
    if ($WorkingDirectory) {
        Write-Host "[$WorkingDirectory] $display" -ForegroundColor DarkGray
        & git -C $WorkingDirectory @Arguments
    } else {
        Write-Host $display -ForegroundColor DarkGray
        & git @Arguments
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: $display"
    }
}

Require-Command git

$targetRootItem = Get-Item -LiteralPath $TargetRoot -ErrorAction SilentlyContinue
if (-not $targetRootItem) {
    Write-Step "Creating target root: $TargetRoot"
    New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
}

$DestinationPath = Join-Path $TargetRoot $DestinationName
Write-Step "Target checkout: $DestinationPath"

if (Test-Path -LiteralPath $DestinationPath) {
    $gitDir = Join-Path $DestinationPath '.git'

    if (-not (Test-Path -LiteralPath $gitDir)) {
        if (-not $BackupExisting) {
            throw "Destination exists but is not a git checkout: $DestinationPath. Re-run with -BackupExisting or choose a different -DestinationName."
        }

        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backupPath = "$DestinationPath.backup-$timestamp"
        Write-Step "Backing up existing non-git folder to: $backupPath"
        Move-Item -LiteralPath $DestinationPath -Destination $backupPath
    }
}

if (-not (Test-Path -LiteralPath $DestinationPath)) {
    Write-Step "Cloning $RepoUrl branch $Branch"
    Invoke-Git -Arguments @('clone', '--branch', $Branch, '--single-branch', $RepoUrl, $DestinationPath)
} else {
    Write-Step "Updating existing checkout"
    Invoke-Git -WorkingDirectory $DestinationPath -Arguments @('remote', 'set-url', 'origin', $RepoUrl)
    Invoke-Git -WorkingDirectory $DestinationPath -Arguments @('fetch', 'origin', $Branch)
    Invoke-Git -WorkingDirectory $DestinationPath -Arguments @('checkout', $Branch)

    if ($ForceReset) {
        Write-Step "Force-resetting checkout to origin/$Branch"
        Invoke-Git -WorkingDirectory $DestinationPath -Arguments @('reset', '--hard', "origin/$Branch")
        Invoke-Git -WorkingDirectory $DestinationPath -Arguments @('clean', '-fd')
    } else {
        Write-Step "Fast-forwarding checkout"
        Invoke-Git -WorkingDirectory $DestinationPath -Arguments @('pull', '--ff-only', 'origin', $Branch)
    }
}

Write-Step "Checkout status"
Invoke-Git -WorkingDirectory $DestinationPath -Arguments @('status', '--short', '--branch')

if ($InstallDependencies) {
    Write-Step "Installing Python and Node dependencies"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv was not found on PATH. Install uv or omit -InstallDependencies."
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found on PATH. Install Node.js/npm or omit -InstallDependencies."
    }

    Push-Location $DestinationPath
    try {
        & uv sync
        if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }

        & npm install
        if ($LASTEXITCODE -ne 0) { throw 'root npm install failed' }

        & npm install --prefix frontend
        if ($LASTEXITCODE -ne 0) { throw 'frontend npm install failed' }
    } finally {
        Pop-Location
    }
}

Write-Step "Ready"
Write-Host "Repository copied to: $DestinationPath" -ForegroundColor Green
Write-Host "Branch: $Branch" -ForegroundColor Green

Write-Host "`nNext commands:" -ForegroundColor Yellow
Write-Host "cd /d `"$DestinationPath`""
Write-Host "uv sync"
Write-Host "npm install"
Write-Host "npm install --prefix frontend"
Write-Host "npm run desktop:start"

if ($StartDesktop) {
    Write-Step "Starting Electron desktop wrapper"
    Push-Location $DestinationPath
    try {
        & npm run desktop:start
        if ($LASTEXITCODE -ne 0) { throw 'npm run desktop:start failed' }
    } finally {
        Pop-Location
    }
}
