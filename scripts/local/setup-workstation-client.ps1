<#
.SYNOPSIS
Configure any Windows PC to connect to the Hetzner Linux workstation over Tailscale SSH, then optionally launch Remote Desktop.

.DESCRIPTION
This script is intentionally dynamic. It asks for all machine-specific values instead
of hardcoding the server hostname, SSH user, SSH alias, public IP, or RDP target.

It will:
  - Check for OpenSSH client.
  - Check for Tailscale and offer to install it with winget if missing.
  - Start Tailscale login if the PC is not authenticated.
  - Prompt for the workstation Tailscale hostname/IP and SSH user.
  - Write an idempotent SSH alias to $HOME\.ssh\config.
  - Test Tailscale reachability, SSH access, and optional sudo access.
  - Optionally verify that public-IP SSH is blocked.
  - After successful tests, optionally launch Windows Remote Desktop to the workstation over Tailscale.

It does not enable public SSH and does not open firewall ports.

.PARAMETER WorkstationHost
Tailscale MagicDNS hostname or 100.x.y.z address for the workstation.

.PARAMETER WorkstationUser
SSH username on the workstation. Defaults to agent.

.PARAMETER SshAlias
Local SSH config alias to create. Defaults to ai-workstation.

.PARAMETER PublicIp
Optional Hetzner public IP. If provided, the script verifies public SSH fails.

.PARAMETER RdpHost
Optional RDP host. Defaults to WorkstationHost.

.PARAMETER RdpPort
Optional RDP port. Defaults to 3389.

.PARAMETER RdpUser
Optional RDP username. Defaults to WorkstationUser.

.PARAMETER SkipInstall
Do not offer to install Tailscale when missing.

.PARAMETER SkipSudoCheck
Do not require sudo -n to pass on the server.

.PARAMETER SkipRdpLaunch
Do not launch Remote Desktop after successful tests.

.EXAMPLE
.\scripts\local\setup-workstation-client.ps1

.EXAMPLE
.\scripts\local\setup-workstation-client.ps1 -WorkstationHost <hostname> -WorkstationUser agent -SshAlias ai-workstation
#>

[CmdletBinding()]
param(
    [string]$WorkstationHost,
    [string]$WorkstationUser,
    [string]$SshAlias,
    [string]$PublicIp,
    [string]$RdpHost,
    [int]$RdpPort = 3389,
    [string]$RdpUser,
    [switch]$SkipInstall,
    [switch]$SkipSudoCheck,
    [switch]$SkipRdpLaunch
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format HH:mm:ss)] $Message"
}

function Write-Fail {
    param([string]$Message)
    Write-Error "[$(Get-Date -Format HH:mm:ss)] $Message"
}

function Read-DefaultedInput {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [string]$DefaultValue,
        [switch]$Required
    )

    while ($true) {
        if ([string]::IsNullOrWhiteSpace($DefaultValue)) {
            $value = Read-Host $Prompt
        } else {
            $value = Read-Host "$Prompt [$DefaultValue]"
            if ([string]::IsNullOrWhiteSpace($value)) {
                $value = $DefaultValue
            }
        }

        if (-not $Required -or -not [string]::IsNullOrWhiteSpace($value)) {
            if ($null -eq $value) { return "" }
            return $value.Trim()
        }

        Write-Host "A value is required."
    }
}

function Read-YesNo {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [bool]$DefaultYes = $true
    )

    $suffix = if ($DefaultYes) { "[Y/n]" } else { "[y/N]" }
    $raw = Read-Host "$Prompt $suffix"
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $DefaultYes
    }
    return $raw.Trim().ToLowerInvariant().StartsWith("y")
}

function Find-CommandPath {
    param([Parameter(Mandatory = $true)][string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Find-TailscaleExe {
    $fromPath = Find-CommandPath "tailscale.exe"
    if ($fromPath) { return $fromPath }

    $candidates = @(
        "$env:ProgramFiles\Tailscale\tailscale.exe",
        "${env:ProgramFiles(x86)}\Tailscale\tailscale.exe",
        "$env:LocalAppData\Tailscale\tailscale.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Ensure-OpenSshClient {
    $ssh = Find-CommandPath "ssh.exe"
    if ($ssh) {
        Write-Step "OpenSSH client found: $ssh"
        return $ssh
    }

    Write-Fail "OpenSSH client was not found. Install Windows OpenSSH Client, then rerun this script."
    exit 1
}

function Ensure-Tailscale {
    $tailscale = Find-TailscaleExe
    if ($tailscale) {
        Write-Step "Tailscale CLI found: $tailscale"
        return $tailscale
    }

    if ($SkipInstall) {
        Write-Fail "Tailscale is not installed and -SkipInstall was supplied. Install Tailscale, join the tailnet, then rerun this script."
        exit 1
    }

    $install = Read-YesNo "Tailscale is not installed. Install it now with winget?" $true
    if (-not $install) {
        Write-Fail "Tailscale is required. Install it, join the same tailnet as the workstation, then rerun this script."
        Start-Process "https://tailscale.com/download/windows"
        exit 1
    }

    $winget = Find-CommandPath "winget.exe"
    if (-not $winget) {
        Write-Fail "winget.exe was not found. Install Tailscale manually, then rerun this script."
        Start-Process "https://tailscale.com/download/windows"
        exit 1
    }

    Write-Step "Installing Tailscale with winget..."
    & $winget install --id Tailscale.Tailscale --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "winget failed to install Tailscale. Install Tailscale manually, then rerun this script."
        exit 1
    }

    Start-Sleep -Seconds 3
    $tailscale = Find-TailscaleExe
    if (-not $tailscale) {
        Write-Fail "Tailscale installation completed but tailscale.exe was not found. Restart PowerShell or install manually, then rerun."
        exit 1
    }

    return $tailscale
}

function Ensure-TailscaleLogin {
    param([Parameter(Mandatory = $true)][string]$TailscaleExe)

    & $TailscaleExe status *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Step "Tailscale is authenticated."
        return
    }

    Write-Step "Tailscale is installed but not authenticated. Starting Tailscale login."
    Write-Host "A browser login may open. Complete login, then return to this window."
    & $TailscaleExe up

    & $TailscaleExe status *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Tailscale is still not authenticated. Complete Tailscale login, then rerun this script."
        exit 1
    }
}

function Test-TailscaleReachability {
    param(
        [Parameter(Mandatory = $true)][string]$TailscaleExe,
        [Parameter(Mandatory = $true)][string]$HostName
    )

    Write-Step "Testing Tailscale reachability to $HostName..."
    & $TailscaleExe ping $HostName
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Could not reach $HostName over Tailscale. Verify MagicDNS/hostname, tailnet membership, and ACLs/grants."
        exit 1
    }
}

function Update-SshConfig {
    param(
        [Parameter(Mandatory = $true)][string]$Alias,
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][string]$UserName
    )

    $sshDir = Join-Path $HOME ".ssh"
    $sshConfig = Join-Path $sshDir "config"
    $markerBegin = "# >>> ai-workstation tailscale alias >>>"
    $markerEnd = "# <<< ai-workstation tailscale alias <<<"

    if (-not (Test-Path $sshDir)) {
        New-Item -ItemType Directory -Path $sshDir | Out-Null
    }

    if (-not (Test-Path $sshConfig)) {
        New-Item -ItemType File -Path $sshConfig | Out-Null
    }

    $existing = Get-Content $sshConfig -Raw -ErrorAction SilentlyContinue
    if ($null -eq $existing) { $existing = "" }

    $escapedBegin = [regex]::Escape($markerBegin)
    $escapedEnd = [regex]::Escape($markerEnd)
    $pattern = "(?s)$escapedBegin.*?$escapedEnd\r?\n?"
    $cleaned = [regex]::Replace($existing, $pattern, "")

    $block = @"
$markerBegin
Host $Alias
  HostName $HostName
  User $UserName
  Port 22
  ServerAliveInterval 30
  ServerAliveCountMax 3
  ForwardAgent no
$markerEnd
"@

    $newContent = $cleaned.TrimEnd() + "`r`n" + $block + "`r`n"
    Set-Content -Path $sshConfig -Value $newContent -Encoding ascii
    Write-Step "Wrote SSH alias '$Alias' to $sshConfig"
}

function Test-SshAccess {
    param(
        [Parameter(Mandatory = $true)][string]$Alias,
        [bool]$RequireSudo
    )

    $remoteCommand = if ($RequireSudo) {
        "hostname; whoami; tailscale ip -4; sudo -n true && echo sudo-ok"
    } else {
        "hostname; whoami; tailscale ip -4"
    }

    Write-Step "Testing SSH access through alias '$Alias'..."
    ssh.exe -o BatchMode=yes -o ConnectTimeout=15 $Alias $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "SSH failed. Verify Tailscale SSH policy allows this Windows PC/user to connect as the selected workstation user."
        exit 1
    }
}

function Test-PublicSshBlocked {
    param(
        [string]$PublicAddress,
        [string]$UserName
    )

    if ([string]::IsNullOrWhiteSpace($PublicAddress)) {
        return
    }

    Write-Step "Verifying public SSH is blocked for $PublicAddress..."
    ssh.exe -o BatchMode=yes -o ConnectTimeout=5 "$UserName@$PublicAddress" "echo should-not-connect" *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Fail "Public SSH to $PublicAddress succeeded. This violates the Tailscale-only SSH policy. Block TCP/22 at the provider firewall and verify OpenSSH is localhost-only."
        exit 1
    }

    ssh.exe -p 2222 -o BatchMode=yes -o ConnectTimeout=5 "$UserName@$PublicAddress" "echo should-not-connect" *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Fail "Public SSH to $PublicAddress:2222 succeeded. The localhost fallback must not be public."
        exit 1
    }

    Write-Step "Public SSH checks failed as expected."
}

function Test-RdpPort {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port
    )

    Write-Step "Testing RDP TCP reachability to ${HostName}:$Port..."
    $result = Test-NetConnection -ComputerName $HostName -Port $Port -InformationLevel Quiet
    if (-not $result) {
        Write-Fail "RDP port ${HostName}:$Port is not reachable. Verify xRDP is running and Tailscale ACLs/grants allow tcp:$Port."
        exit 1
    }
}

function Start-RemoteDesktop {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [string]$UserName
    )

    $mstsc = Find-CommandPath "mstsc.exe"
    if (-not $mstsc) {
        Write-Fail "mstsc.exe was not found. Remote Desktop Client is required to launch RDP."
        exit 1
    }

    $rdpPath = Join-Path $env:TEMP "ai-workstation-$([guid]::NewGuid().ToString('N')).rdp"
    $fullAddress = if ($Port -eq 3389) { $HostName } else { "${HostName}:$Port" }
    $usernameLine = if ([string]::IsNullOrWhiteSpace($UserName)) { "" } else { "username:s:$UserName`r`n" }

    $rdpContent = @"
screen mode id:i:2
use multimon:i:1
desktopwidth:i:1920
desktopheight:i:1080
session bpp:i:32
full address:s:$fullAddress
prompt for credentials:i:1
$usernameLine`nredirectclipboard:i:1
redirectprinters:i:0
redirectsmartcards:i:0
redirectcomports:i:0
redirectposdevices:i:0
authentication level:i:2
"@

    Set-Content -Path $rdpPath -Value $rdpContent -Encoding ascii
    Write-Step "Launching Remote Desktop to $fullAddress..."
    Start-Process -FilePath $mstsc -ArgumentList @($rdpPath)
}

$sshPath = Ensure-OpenSshClient
$tailscalePath = Ensure-Tailscale
Ensure-TailscaleLogin -TailscaleExe $tailscalePath

if ([string]::IsNullOrWhiteSpace($WorkstationHost)) {
    $WorkstationHost = Read-DefaultedInput -Prompt "Workstation Tailscale hostname or 100.x.y.z address" -Required
}

if ([string]::IsNullOrWhiteSpace($WorkstationUser)) {
    $WorkstationUser = Read-DefaultedInput -Prompt "Workstation SSH user" -DefaultValue "agent" -Required
}

if ([string]::IsNullOrWhiteSpace($SshAlias)) {
    $SshAlias = Read-DefaultedInput -Prompt "Local SSH alias" -DefaultValue "ai-workstation" -Required
}

if ([string]::IsNullOrWhiteSpace($PublicIp)) {
    $PublicIp = Read-DefaultedInput -Prompt "Optional Hetzner public IP to verify blocked public SSH; leave blank to skip" -DefaultValue ""
}

$requireSudo = -not $SkipSudoCheck
if ($requireSudo) {
    $requireSudo = Read-YesNo "Require passwordless sudo check on the workstation?" $true
}

Test-TailscaleReachability -TailscaleExe $tailscalePath -HostName $WorkstationHost
Update-SshConfig -Alias $SshAlias -HostName $WorkstationHost -UserName $WorkstationUser
Test-SshAccess -Alias $SshAlias -RequireSudo $requireSudo
Test-PublicSshBlocked -PublicAddress $PublicIp -UserName $WorkstationUser

$launchRdp = -not $SkipRdpLaunch
if ($launchRdp) {
    $launchRdp = Read-YesNo "SSH tests passed. Launch Remote Desktop over Tailscale now?" $true
}

if ($launchRdp) {
    if ([string]::IsNullOrWhiteSpace($RdpHost)) {
        $RdpHost = Read-DefaultedInput -Prompt "RDP host" -DefaultValue $WorkstationHost -Required
    }

    if ($RdpPort -le 0 -or $RdpPort -gt 65535) {
        $RdpPort = 3389
    }

    $rdpPortInput = Read-DefaultedInput -Prompt "RDP port" -DefaultValue $RdpPort.ToString() -Required
    $parsedPort = 0
    if (-not [int]::TryParse($rdpPortInput, [ref]$parsedPort) -or $parsedPort -le 0 -or $parsedPort -gt 65535) {
        Write-Fail "Invalid RDP port: $rdpPortInput"
        exit 1
    }
    $RdpPort = $parsedPort

    if ([string]::IsNullOrWhiteSpace($RdpUser)) {
        $RdpUser = Read-DefaultedInput -Prompt "RDP username" -DefaultValue $WorkstationUser
    }

    Test-RdpPort -HostName $RdpHost -Port $RdpPort
    Start-RemoteDesktop -HostName $RdpHost -Port $RdpPort -UserName $RdpUser
}

Write-Host ""
Write-Host "Configured local Windows access:"
Write-Host "  ssh $SshAlias"
Write-Host ""
Write-Host "Private UI forwarding:"
Write-Host "  ssh -N -L 9877:localhost:9877 -L 4000:localhost:4000 -L 3000:localhost:3000 $SshAlias"
Write-Host ""
Write-Host "Then open locally:"
Write-Host "  http://localhost:9877     Control Plane"
Write-Host "  http://localhost:4000/ui  LiteLLM"
Write-Host "  http://localhost:3000     OpenHands, if running there"
Write-Host ""
Write-Host "Do not use the Hetzner public IP for SSH."
