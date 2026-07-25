"""Windows maintenance tools powered by PowerShell subprocess execution.

This module is a Python-side catalogue of every feature in the standalone
``SA WinTools Professional`` suite (the PowerShell app that lives in
``tools source/``). Each tool maps to one or more *modes*, and each mode
carries a PowerShell script body ported verbatim from
``tools source/SA_WinTools_Buttons.ps1``.

The GUI (``gui.py``) runs these scripts as non-interactive PowerShell
subprocesses with stdout/stderr captured and streamed live into a log
panel. The scripts themselves are unchanged in behaviour; only the
``$using:<var>`` job-scoped variables have been replaced with plain
``__PLACEHOLDER__`` tokens that the GUI substitutes before execution.

Why PowerShell (and not a native re-implementation)?
  The tools wrap command-line utilities and cmdlets that have no Python
  equivalent (``sfc``, ``dism``, ``chkdsk``, ``Optimize-Volume``,
  ``Get-PnpDevice``, ``Get-WinEvent``, ``Clear-RecycleBin``, ``reagentc``,
  ``slmgr.vbs``, ``w32tm``, ``powercfg``, ``netsh`` ...). Reusing the
  tested scripts guarantees feature parity with the original suite.

Substitution tokens (replaced by the GUI before running):
  ``__LIB__``      - absolute path to ``SA_WinTools_Lib.ps1``
  ``__BACKUP__``   - registry backup root folder
  ``__DRIVE__``    - a bare drive letter, e.g. ``C``
  ``__MODE__``     - chkdsk mode flag, e.g. ``/r`` or empty
  ``__INPUT__``    - free-form text input (product key / Wi-Fi profile)
  ``__PATHS__``    - newline-separated paths / package FullNames chosen by
                     the user in a ``path_select`` mode's pick dialog
"""

from __future__ import annotations

import os

# Directory containing this file (the app root).
_APP_DIR = os.path.dirname(os.path.abspath(__file__))

# The shared PowerShell library used by the Install/Uninstall tools.
LIB_PATH = os.path.join(_APP_DIR, "tools source", "SA_WinTools_Lib.ps1")

# Where registry backups are written by the Install/Uninstall *Fix* mode.
BACKUP_ROOT = os.path.join(_APP_DIR, "SA_WinTools_RegBackup")


# ---------------------------------------------------------------------------
#  Shared script preamble (prepended to every tool script at run time)
# ---------------------------------------------------------------------------
# - SilentlyContinue: suppresses Write-Progress bars that would otherwise
#   leak to a hidden console and stall streaming output.
# - UTF-8 output encoding so box-drawing / accented characters render.
PREAMBLE = r"""$ProgressPreference='SilentlyContinue'
$ErrorActionPreference='Continue'
$FormatEnumerationLimit=-1
try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}
"""


# ---------------------------------------------------------------------------
#  Row 1 - System Repair
# ---------------------------------------------------------------------------
_SFC = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - SFC System File Checker (sfc /scannow)'
Write-Output '============================================================'
Write-Output ''
sfc /scannow *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] SFC scan completed.'
Write-Output '============================================================'
"""

_DISM_CLEAN = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - DISM Component Cleanup'
Write-Output '============================================================'
Write-Output ''
dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] DISM component cleanup completed.'
Write-Output '============================================================'
"""

_DISM_REPAIR = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - DISM RestoreHealth'
Write-Output '============================================================'
Write-Output ''
dism.exe /Online /Cleanup-Image /RestoreHealth *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] DISM repair completed.'
Write-Output '============================================================'
"""

_FIX_WINUPDATE = r"""$s = @('wuauserv', 'bits', 'cryptsvc', 'appidsvc')
Write-Output '[STEP 1] Stopping Services...'
foreach ($n in $s) { Stop-Service $n -Force -EA 0; Write-Output "  Stopped $n" }
Write-Output '[STEP 2] Renaming Folders...'
if (Test-Path "$env:SystemRoot\SoftwareDistribution") {
    Rename-Item "$env:SystemRoot\SoftwareDistribution" 'SoftwareDistribution.old' -Force -EA 0
}
if (Test-Path "$env:SystemRoot\System32\catroot2") {
    Rename-Item "$env:SystemRoot\System32\catroot2" 'catroot2.old' -Force -EA 0
}
Write-Output '[STEP 3] Resetting Network...'
netsh winsock reset *>&1 | Write-Output
Write-Output '[STEP 4] Restarting Services...'
foreach ($n in $s) { Write-Output "  Starting $n..."; Start-Service $n -EA 0 }
Write-Output '[SUCCESS] Windows Update Fix Applied.'
"""

_WINRE = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Windows Recovery Environment (WinRE)'
Write-Output '============================================================'
Write-Output ''
Write-Output '[STEP 1] Querying current WinRE status...'
$info = reagentc /info
$info | Write-Output
if ($info -like '*Windows RE status:*Disabled*') {
    Write-Output ''
    Write-Output '[STEP 2] Status is DISABLED. Attempting to enable...'
    reagentc /enable *>&1 | Write-Output
    Write-Output ''
    Write-Output '[STEP 3] Re-verifying Status...'
    reagentc /info *>&1 | Write-Output
} else {
    Write-Output ''
    Write-Output '[INFO] Windows RE is already ENABLED.'
}
Write-Output ''
Write-Output '[SUCCESS] WinRE Manager task completed.'
Write-Output '============================================================'
"""


# ---------------------------------------------------------------------------
#  Row 2 - Maintenance
# ---------------------------------------------------------------------------
_CLEANUP = r"""$cleanupTargets = @(
    @{ Name='User Temp';             Path="$env:TEMP";                                                              Wildcard=$false }
    @{ Name='Windows Temp';          Path="$env:SystemRoot\Temp";                                                   Wildcard=$false }
    @{ Name='SoftwareDistribution';  Path="$env:SystemRoot\SoftwareDistribution";                                   Wildcard=$false }
    @{ Name='Prefetch';              Path="$env:SystemRoot\Prefetch";                                               Wildcard=$false }
    @{ Name='Error Reporting (WER)'; Path="$env:LOCALAPPDATA\Microsoft\Windows\WER";                                Wildcard=$false }
    @{ Name='CBS Logs';              Path="$env:SystemRoot\Logs\CBS\*.log";                                         Wildcard=$true  }
    @{ Name='DISM Logs';             Path="$env:SystemRoot\Logs\DISM\*.log";                                        Wildcard=$true  }
    @{ Name='Defender Scan History'; Path="$env:ProgramData\Microsoft\Windows Defender\Scans\History\Results";      Wildcard=$false }
    @{ Name='Thumbnail Cache';       Path="$env:LOCALAPPDATA\Microsoft\Windows\Explorer\thumbcache_*.db";           Wildcard=$true  }
    @{ Name='Icon Cache';            Path="$env:LOCALAPPDATA\Microsoft\Windows\Explorer\iconcache_*.db";            Wildcard=$true  }
    @{ Name='Font Cache';            Path="$env:SystemRoot\ServiceProfiles\LocalService\AppData\Local\FontCache";   Wildcard=$false }
    @{ Name='System Crash Dump';     Path="$env:SystemRoot\MEMORY.DMP";                                             Wildcard=$true  }
    @{ Name='Mini Crash Dumps';      Path="$env:SystemRoot\Minidump\*";                                             Wildcard=$true  }
    @{ Name='App Crash Dumps';       Path="$env:LOCALAPPDATA\CrashDumps\*";                                        Wildcard=$true  }
    @{ Name='Update Download Cache'; Path="$env:SystemRoot\SoftwareDistribution\Download\*";                        Wildcard=$true  }
    @{ Name='Delivery Optimization'; Path="$env:SystemRoot\SoftwareDistribution\DeliveryOptimization\*";            Wildcard=$true  }
)

function Get-PathSize($TargetPath, $IsWildcard) {
    $total = 0
    try {
        if ($IsWildcard) {
            $items = Get-Item $TargetPath -Force -EA 0
            foreach ($item in $items) {
                if ($item.PSIsContainer) {
                    $s = (Get-ChildItem $item.FullName -Recurse -Force -File -EA 0 | Measure-Object -Property Length -Sum).Sum
                    if ($s) { $total += $s }
                } else { $total += $item.Length }
            }
        } else {
            if (Test-Path $TargetPath) {
                $s = (Get-ChildItem $TargetPath -Recurse -Force -File -EA 0 | Measure-Object -Property Length -Sum).Sum
                if ($s) { $total += $s }
            }
        }
    } catch {}
    return $total
}
function Get-PathItemCount($TargetPath, $IsWildcard) {
    try {
        if ($IsWildcard) { return (Get-Item $TargetPath -Force -EA 0 | Measure-Object).Count }
        else { if (Test-Path $TargetPath) { return (Get-ChildItem $TargetPath -Force -EA 0 | Measure-Object).Count } }
    } catch {}
    return 0
}
function Remove-PathContents($TargetPath, $IsWildcard) {
    try {
        if ($IsWildcard) { Get-Item $TargetPath -Force -EA 0 | Remove-Item -Recurse -Force -EA 0 }
        else { if (Test-Path $TargetPath) { Get-ChildItem $TargetPath -Recurse -Force -EA 0 | Remove-Item -Recurse -Force -EA 0 } }
    } catch {}
}

Write-Output '[*] Initializing system scan...'
Write-Output ''
$totalBefore = 0
foreach ($t in $cleanupTargets) { $totalBefore += Get-PathSize $t.Path $t.Wildcard }
$mbBefore = [Math]::Round($totalBefore / 1MB, 2)
Write-Output "[PRE-SCAN] Total reclaimable: ~$mbBefore MB"
Write-Output ''

foreach ($t in $cleanupTargets) {
    $count = Get-PathItemCount $t.Path $t.Wildcard
    if ($count -eq 0) { Write-Output "[-] $($t.Name) -> Already empty."; continue }
    $mb = [Math]::Round((Get-PathSize $t.Path $t.Wildcard) / 1MB, 2)
    Write-Output "[-] $($t.Name) ($count items, $mb MB). Cleaning..."
    Remove-PathContents $t.Path $t.Wildcard
    $remaining = Get-PathItemCount $t.Path $t.Wildcard
    if ($remaining -gt 0) { Write-Output "    [!] $remaining items in-use (locked)." }
    else { Write-Output '    [OK] Cleared.' }
}

Write-Output ''
Write-Output '[*] Emptying Recycle Bin...'
Clear-RecycleBin -Confirm:$false -EA 0

$totalAfter = 0
foreach ($t in $cleanupTargets) { $totalAfter += Get-PathSize $t.Path $t.Wildcard }
$mbAfter   = [Math]::Round($totalAfter / 1MB, 2)
$reclaimed = [Math]::Round($mbBefore - $mbAfter, 2)
if ($reclaimed -lt 0) { $reclaimed = 0 }

Write-Output ''
Write-Output '======================================='
Write-Output ' CLEANUP SUMMARY'
Write-Output '======================================='
Write-Output " Before    : $mbBefore MB"
Write-Output " After     : $mbAfter MB"
Write-Output " Reclaimed : $reclaimed MB"
Write-Output '======================================='
"""

_DISK_LARGE_FILES = r"""$root = '__DRIVE__:\'
Write-Output '============================================================'
Write-Output " SA WinTools - Large Files on $root (over 500 MB)"
Write-Output '============================================================'
Write-Output ''
Write-Output "[*] Scanning $root for files over 500 MB..."
Write-Output ''
$found = Get-ChildItem $root -Recurse -File -EA SilentlyContinue |
    Where-Object { $_.Length -gt 500MB } |
    Sort-Object Length -Descending |
    Select-Object @{n='Size(MB)'; e={[math]::Round($_.Length/1MB,1)}}, FullName
if ($found) {
    $found | Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
    Write-Output "[INFO] $($found.Count) file(s) over 500 MB found."
} else { Write-Output "[OK] No files over 500 MB found on $root" }
Write-Output '[SUCCESS] Large file scan completed.'
Write-Output '============================================================'
"""

_DISK_TOP_FOLDERS = r"""$root = '__DRIVE__:\'
Write-Output '============================================================'
Write-Output " SA WinTools - Top 10 Largest Folders on $root"
Write-Output '============================================================'
Write-Output ''
Write-Output "[*] Calculating folder sizes on $root..."
Write-Output ''
Get-ChildItem $root -Directory -EA SilentlyContinue | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse -File -EA SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
    [PSCustomObject]@{ 'Size(GB)' = [math]::Round($size/1GB, 2); Folder = $_.FullName }
} | Sort-Object 'Size(GB)' -Descending | Select-Object -First 10 |
    Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
Write-Output '[SUCCESS] Top folder analysis completed.'
Write-Output '============================================================'
"""

_DISK_FOLDER_MAP = r"""$root = '__DRIVE__:\'
Write-Output '============================================================'
Write-Output " SA WinTools - Folder Size Map (Recursive) on $root"
Write-Output '============================================================'
Write-Output ''
Write-Output "[*] Phase 1: Enumerating directories under $root ..."
$rootPath = $root.TrimEnd('\')
$allDirs = @(Get-ChildItem $root -Recurse -Directory -Force -EA SilentlyContinue)
$dirList = @($rootPath) + ($allDirs | ForEach-Object { $_.FullName })
Write-Output "[*] Found $($dirList.Count) directories."
Write-Output ''
Write-Output '[*] Phase 2: Summing direct file sizes per directory...'
$directSize = @{}
foreach ($d in $dirList) { $directSize[$d] = [long]0 }
$fileCount = 0
Get-ChildItem $root -Recurse -File -Force -EA SilentlyContinue | ForEach-Object {
    $parent = Split-Path $_.FullName -Parent
    if ($directSize.ContainsKey($parent)) {
        $directSize[$parent] += $_.Length
    } else {
        $directSize[$parent] = $_.Length
    }
    $fileCount++
}
Write-Output "[*] Processed $fileCount files."
Write-Output ''
Write-Output '[*] Phase 3: Propagating sizes upward (deepest first)...'
$sorted = $directSize.Keys | Sort-Object { ($_ -split '\\').Count } -Descending
foreach ($d in $sorted) {
    $parent = Split-Path $d -Parent
    if ($parent -and $directSize.ContainsKey($parent) -and $parent -ne $d) {
        $directSize[$parent] += $directSize[$d]
    }
}
Write-Output '[*] Done. Top 20 largest directories:'
Write-Output ''
$directSize.GetEnumerator() |
    Where-Object { $_.Value -gt 0 } |
    Sort-Object Value -Descending |
    Select-Object -First 20 |
    ForEach-Object {
        [PSCustomObject]@{
            'Size(MB)' = [math]::Round($_.Value/1MB, 1)
            'Size(GB)' = [math]::Round($_.Value/1GB, 2)
            Path = $_.Key
        }
    } | Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
Write-Output "[INFO] Showing top 20 of $($directSize.Count) directories."
Write-Output '[SUCCESS] Folder size map completed.'
Write-Output '============================================================'
"""

_DISK_TOP_FILES = r"""$root = '__DRIVE__:\'
Write-Output '============================================================'
Write-Output " SA WinTools - Top 50 Biggest Files on $root"
Write-Output '============================================================'
Write-Output ''
Write-Output "[*] Scanning $root for the biggest files..."
Write-Output ''
$found = Get-ChildItem $root -Recurse -File -EA SilentlyContinue |
    Sort-Object Length -Descending |
    Select-Object -First 50 @{n='Size(MB)'; e={[math]::Round($_.Length/1MB,1)}}, FullName
if ($found) {
    $found | Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
    Write-Output "[INFO] Showing top 50 biggest files on $root."
} else { Write-Output "[OK] No files found on $root" }
Write-Output '[SUCCESS] Top files scan completed.'
Write-Output '============================================================'
"""

_DISK_DUPLICATES = r"""$root = '__DRIVE__:\'
Write-Output '============================================================'
Write-Output " SA WinTools - Duplicate File Finder on $root"
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Phase 1: Scanning files...'
$files = @(Get-ChildItem $root -Recurse -File -EA SilentlyContinue)
Write-Output "[*] Found $($files.Count) files."
Write-Output ''
Write-Output '[*] Phase 2: Grouping by size...'
$bySize = @{}
foreach ($f in $files) {
    if (-not $bySize.ContainsKey($f.Length)) {
        $bySize[$f.Length] = New-Object System.Collections.Generic.List[PSObject]
    }
    $bySize[$f.Length].Add($f)
}
$duplicateSizes = @($bySize.Keys | Where-Object { $bySize[$_].Count -gt 1 })
Write-Output "[*] Found $($duplicateSizes.Count) size groups with potential duplicates."
Write-Output ''
Write-Output '[*] Phase 3: Hashing same-size files (SHA1)...'
$hashGroups = @{}
$hashCount = 0
foreach ($size in $duplicateSizes) {
    foreach ($f in $bySize[$size]) {
        try {
            $hash = (Get-FileHash $f.FullName -Algorithm SHA1 -EA Stop).Hash
        } catch {
            $hash = "ERROR-$($f.FullName)"
        }
        if (-not $hashGroups.ContainsKey($hash)) {
            $hashGroups[$hash] = New-Object System.Collections.Generic.List[PSObject]
        }
        $hashGroups[$hash].Add($f)
        $hashCount++
    }
}
Write-Output "[*] Computed $hashCount file hashes."
Write-Output ''
Write-Output '[*] Phase 4: Reporting duplicates...'
$duplicates = @($hashGroups.Values | Where-Object { $_.Count -gt 1 })
if ($duplicates.Count -eq 0) {
    Write-Output '[OK] No duplicate files found.'
} else {
    $totalWasted = [long]0
    foreach ($group in $duplicates) {
        $wasted = $group[0].Length * ($group.Count - 1)
        $totalWasted += $wasted
        Write-Output ''
        Write-Output ("[DUP] Size: $([math]::Round($group[0].Length/1MB, 1)) MB  Count: $($group.Count)  Wasted: $([math]::Round($wasted/1MB, 1)) MB")
        $group | ForEach-Object { Write-Output "      $($_.FullName)" }
    }
    Write-Output ''
    Write-Output '======================================='
    Write-Output ' DUPLICATE SCAN SUMMARY'
    Write-Output '======================================='
    Write-Output "  Duplicate groups : $($duplicates.Count)"
    Write-Output "  Wasted space     : $([math]::Round($totalWasted/1MB, 1)) MB ($([math]::Round($totalWasted/1GB, 2)) GB)"
    Write-Output '======================================='
}
Write-Output '[SUCCESS] Duplicate file scan completed.'
Write-Output '============================================================'
"""

_RESET_SPOOLER = r"""Write-Output '[STEP 1] Stopping Spooler...'
Stop-Service 'Spooler' -Force -EA 0
Write-Output '[STEP 2] Clearing print queue...'
Get-ChildItem "$env:SystemRoot\System32\spool\PRINTERS\*" -Recurse -EA 0 | Remove-Item -Force -Recurse -EA 0
Write-Output '[STEP 3] Restarting Spooler...'
Start-Service 'Spooler' -EA 0
Write-Output '[SUCCESS] Spooler reset completed.'
"""

_INSTALL_SCAN = r""". "__LIB__"
Write-Output '============================================================'
Write-Output ' SA WinTools - Install/Uninstall SCAN (Read-Only)'
Write-Output '============================================================'
Write-Output ''
Write-Output '[SCANNING] Registry hives + MSI products + patch cache...'
$scan = Invoke-InstallScan
Write-ScanReport -Scan $scan
$highOrphans     = $scan.OrphanedHigh.Count
$brokenCount     = $scan.BrokenEntries.Count
$orphanedMsi     = ($scan.StaleMsiEntries | Where-Object { $_.OrphanedEntry }).Count
$repairableCount = $highOrphans + $brokenCount + $orphanedMsi
Write-Output '============================================================'
Write-Output ' SCAN COMPLETE'
Write-Output '============================================================'
Write-Output "  Safely repairable       : $repairableCount"
Write-Output "    - HIGH conf orphans   : $highOrphans"
Write-Output "    - Broken paths        : $brokenCount"
Write-Output "    - Orphaned MSI        : $orphanedMsi"
Write-Output ''
if ($repairableCount -gt 0) { Write-Output '  >> Use Fix mode to repair with full backup <<' }
else { Write-Output '  STATUS: HEALTHY - No repairable issues found.' }
Write-Output '============================================================'
"""

_INSTALL_FIX = r""". "__LIB__"
$bkRoot = "__BACKUP__"
Write-Output '============================================================'
Write-Output ' SA WinTools - Install/Uninstall REPAIR'
Write-Output '============================================================'
Write-Output ''
$timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$backupDir = Join-Path $bkRoot $timestamp
Write-Output "[STEP 1] Backup directory: $backupDir"
Write-Output ''
Write-Output '[STEP 2] Scanning registry...'
$scan = Invoke-InstallScan
Write-Output "  Scanned $($scan.TotalScanned) uninstall + $($scan.MsiScanned) MSI entries"
Write-Output ''
Write-Output '[STEP 3] Backing up targeted registry keys...'
$targets = Backup-RegistryKeys -BackupDir $backupDir -OrphanedHigh $scan.OrphanedHigh -BrokenEntries $scan.BrokenEntries -StaleMsiEntries $scan.StaleMsiEntries
Write-Output "  Backed up $($targets.Count) keys to: $backupDir"
Write-Output ''
if ($targets.Count -eq 0) {
    Write-Output '[RESULT] No repairable issues found. System is healthy.'
    Write-Output '============================================================'
    return
}
Write-Output "[STEP 4] Executing repairs ($($targets.Count) targets)..."
$result = Invoke-InstallRepair -Targets $targets
foreach ($line in $result.Log) { Write-Output $line }
Write-Output ''
Write-Output '[STEP 5] Post-repair verification...'
Write-PostRepairVerification -UninstallPaths $scan.UninstallPaths
Write-Output ''
if ($scan.DuplicateEntries.Count -gt 0) {
    Write-Output '[INFO] Duplicate program names (manual review recommended):'
    foreach ($d in $scan.DuplicateEntries) { Write-Output "  [$($d.Count)x] $($d.DisplayName)" }
    Write-Output ''
}
Write-Output '============================================================'
Write-Output ' REPAIR COMPLETE'
Write-Output '============================================================'
Write-Output "  Repaired          : $($result.Repaired)"
Write-Output "  Failed            : $($result.Failed)"
Write-Output "  Duplicates (info) : $($scan.DuplicateEntries.Count)"
Write-Output "  Backup location   : $backupDir"
Write-Output ''
Write-Output '  TO UNDO: Double-click any .reg file in the backup folder.'
Write-Output '============================================================'
"""

_FLUSH_DNS = r"""Write-Output '[*] Flushing DNS Resolver Cache...'
ipconfig /flushdns *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] DNS cache flushed. No reboot required.'
"""

_WINSOCK_RESET = r"""Write-Output '[*] Resetting Winsock Catalog...'
netsh winsock reset *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] Winsock reset completed.'
Write-Output '[!] REBOOT REQUIRED for changes to take effect.'
"""

_IP_RESET = r"""Write-Output '[*] Resetting all IP interface configurations...'
netsh int ip reset *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] IP configuration reset completed.'
Write-Output '[!] REBOOT REQUIRED for changes to take effect.'
"""

_RELEASE_IP = r"""Write-Output '[*] Releasing current IP address...'
ipconfig /release *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] IP address released. Network connectivity will drop momentarily.'
"""

_RENEW_IP = r"""Write-Output '[*] Requesting new IP address from DHCP...'
ipconfig /renew *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] IP address renewal requested.'
"""

_RESET_NET_CREDS = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Reset Network Credentials'
Write-Output '============================================================'
Write-Output ''
Write-Output '[STEP 1] Disconnecting all mapped network drives...'
net use * /delete /y *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[STEP 2] Purging cached Kerberos authentication tickets...'
klist purge *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[STEP 3] Hardening SMB guest authentication policy...'
$regPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\LanmanWorkstation'
if (-not (Test-Path $regPath)) { New-Item -Path $regPath -Force | Out-Null }
Set-ItemProperty -Path $regPath -Name 'AllowInsecureGuestAuth' -Value 0 -Type DWord
Write-Output 'SMB guest auth hardened (AllowInsecureGuestAuth = 0)'
Write-Output ''
Write-Output '[STEP 4] Restarting Explorer to flush credential state...'
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process explorer.exe
Write-Output 'Explorer restarted. Network credentials cleared.'
Write-Output ''
Write-Output '[SUCCESS] Network credential reset completed.'
Write-Output '============================================================'
"""


# ---------------------------------------------------------------------------
#  Row 3 - Hardware & Diagnostics
# ---------------------------------------------------------------------------
_TRIM_SSD = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - SSD Trim (ReTrim)'
Write-Output '============================================================'
Write-Output ''
try {
    $ssds = Get-PhysicalDisk -EA SilentlyContinue | Where-Object { $_.MediaType -eq 'SSD' -or $_.FriendlyName -like '*SSD*' -or $_.BusType -eq 'NVMe' }
    if (-not $ssds) {
        $ssdDeviceNumbers = Get-Disk -EA SilentlyContinue | Where-Object { $_.IsSSD -or $_.MediaType -eq 'SSD' -or $_.Model -like '*SSD*' } | Select-Object -ExpandProperty Number -EA SilentlyContinue
    } else {
        $ssdDeviceNumbers = foreach ($s in $ssds) {
            if ($s.DeviceId) { [int]$s.DeviceId } elseif ($s.DeviceNumber) { [int]$s.DeviceNumber } elseif ($s.Number) { [int]$s.Number }
        }
    }
} catch { $ssdDeviceNumbers = $null }

if (-not $ssdDeviceNumbers) {
    Write-Output '[!] No SSD drives detected on this system.'
    Write-Output '============================================================'
    return
}

$ssdVolumes = New-Object System.Collections.Generic.List[PSObject]
$partitions = Get-Partition -EA SilentlyContinue | Where-Object { $ssdDeviceNumbers -contains [int]$_.DiskNumber }
foreach ($p in $partitions) {
    try {
        $v = $p | Get-Volume -EA SilentlyContinue
        if ($v -and $v.DriveLetter -and $v.FileSystem -match 'NTFS|ReFS' -and -not ($ssdVolumes | Where-Object { $_.DriveLetter -eq $v.DriveLetter })) {
            $ssdVolumes.Add($v)
        }
    } catch {}
}
if ($ssdVolumes.Count -eq 0) {
    Write-Output '[!] No accessible NTFS/ReFS volumes found on SSD drives.'
    Write-Output '============================================================'
    return
}

foreach ($v in $ssdVolumes) {
    Write-Output "[*] Trimming volume $($v.DriveLetter): ..."
    Optimize-Volume -DriveLetter $v.DriveLetter -ReTrim -Verbose *>&1 | Out-String -Width 4096 | Write-Output
    Write-Output "    [OK] Trim complete for $($v.DriveLetter):"
    Write-Output ''
}
Write-Output '[SUCCESS] SSD trim operation completed.'
Write-Output '============================================================'
"""

_CHECK_HDD = r"""$drive='__DRIVE__'
$mode='__MODE__'
$modeText = if ($mode) { $mode } else { 'Read-Only' }
Write-Output '============================================================'
Write-Output " SA WinTools - HDD Check (chkdsk)"
Write-Output " Target: $($drive):    Mode: $modeText"
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Initializing chkdsk operation...'
Write-Output '[!] If the drive is in use you may be asked to schedule on restart.'
Write-Output ''
if ($mode) {
    chkdsk "$($drive):" $mode *>&1 | Out-String -Width 4096 | Write-Output
} else {
    chkdsk "$($drive):" *>&1 | Out-String -Width 4096 | Write-Output
}
Write-Output ''
Write-Output '[SUCCESS] Task completed.'
Write-Output '============================================================'
"""

_HID_SERVICES = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - HID Device Services (ROOT\HIDCLASS)'
Write-Output '============================================================'
Write-Output ''
Get-PnpDevice | Where-Object { $_.InstanceId -like 'ROOT\HIDCLASS*' } |
    Select-Object FriendlyName, InstanceId,
        @{n='Service'; e={(Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_Service').Data}} |
    Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
Write-Output '[SUCCESS] HID device services query completed.'
Write-Output '============================================================'
"""

_REMOVE_HID_ERRORS = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Remove Errored ROOT\HIDCLASS Devices'
Write-Output '============================================================'
Write-Output ''
$errorDevices = Get-PnpDevice | Where-Object { $_.InstanceId -like 'ROOT\HIDCLASS*' -and $_.Status -eq 'Error' }
if ($errorDevices) {
    $errorDevices | ForEach-Object {
        Write-Output "Removing: $($_.InstanceId)"
        pnputil /remove-device $_.InstanceId *>&1 | Write-Output
    }
    Write-Output '[SUCCESS] Errored HID device removal completed.'
} else { Write-Output '[INFO] No errored ROOT\HIDCLASS devices found.' }
Write-Output '============================================================'
"""

_BT_RESET = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Reset Bluetooth Adapter'
Write-Output '============================================================'
Write-Output ''
$BTAdapter = Get-PnpDevice -Class Bluetooth -EA SilentlyContinue | Where-Object {
    $_.FriendlyName -match 'Radio|Adapter|Bluetooth' -and
    $_.FriendlyName -notmatch 'Enumerator|Mouse|Keyboard|Headset|Audio|Speaker|Controller'
}
if (-not $BTAdapter) {
    Write-Output '[INFO] No Bluetooth adapter found matching reset criteria.'
    Write-Output '[TIP] Use Bluetooth Adapters (Info) mode to see all detected devices.'
} else {
    foreach ($adapter in $BTAdapter) {
        Write-Output "[*] Resetting: $($adapter.FriendlyName)"
        Disable-PnpDevice -InstanceId $adapter.InstanceId -Confirm:$false -EA SilentlyContinue
        Write-Output '    Disabled. Waiting 2 seconds...'
        Start-Sleep -Seconds 2
        Enable-PnpDevice -InstanceId $adapter.InstanceId -Confirm:$false -EA SilentlyContinue
        Write-Output "    [OK] Reset complete: $($adapter.FriendlyName)"
    }
}
Write-Output ''
Write-Output '[SUCCESS] Bluetooth adapter reset completed.'
Write-Output '============================================================'
"""

_SVC_RESTART = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Restart Stopped Auto-Start Services'
Write-Output '============================================================'
Write-Output ''
$stopped = Get-Service | Where-Object { $_.StartType -eq 'Automatic' -and $_.Status -ne 'Running' }
if ($stopped) {
    foreach ($svc in $stopped) {
        Write-Output "[*] Starting: $($svc.DisplayName) ($($svc.Name))"
        try { Start-Service -Name $svc.Name -EA Stop; Write-Output '    [OK] Started.' }
        catch { Write-Output "    [!] Failed: $($_.Exception.Message)" }
    }
    Write-Output ''
    Write-Output '[*] Post-restart check...'
    Get-Service | Where-Object { $_.StartType -eq 'Automatic' -and $_.Status -ne 'Running' } |
        Select-Object Name, DisplayName, Status | Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
} else { Write-Output '[OK] All Automatic services are already running.' }
Write-Output '[SUCCESS] Service restart pass completed.'
Write-Output '============================================================'
"""


# ---------------------------------------------------------------------------
#  Row 4 - System Info & Status
# ---------------------------------------------------------------------------
_TIME_STATUS = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Windows Time Service Status'
Write-Output '============================================================'
Write-Output ''
w32tm /query /status *>&1 | Write-Output
Write-Output ''
w32tm /query /source *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] Time status query completed.'
Write-Output '============================================================'
"""

_TIME_RESYNC = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Force Time Resync'
Write-Output '============================================================'
Write-Output ''
Write-Output '[STEP 1] Ensuring w32time service is running...'
Start-Service w32time -EA 0
Write-Output '[STEP 2] Forcing resync...'
w32tm /resync /force *>&1 | Write-Output
Write-Output ''
Write-Output '[STEP 3] Verifying result...'
w32tm /query /status *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] Time resync completed.'
Write-Output '============================================================'
"""

_TIME_REREGISTER = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Re-register Windows Time Service'
Write-Output '============================================================'
Write-Output ''
Write-Output '[STEP 1] Stopping w32time...'
Stop-Service w32time -Force -EA 0
Write-Output '[STEP 2] Unregistering service...'
w32tm /unregister *>&1 | Write-Output
Write-Output '[STEP 3] Re-registering service...'
w32tm /register *>&1 | Write-Output
Write-Output '[STEP 4] Starting service...'
Start-Service w32time -EA 0
Write-Output '[STEP 5] Forcing resync...'
w32tm /resync /force *>&1 | Write-Output
Write-Output ''
Write-Output '[STEP 6] Final status check...'
w32tm /query /status *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] Time service re-registration completed.'
Write-Output '============================================================'
"""

_ACT_DETAIL = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Windows License Details (slmgr /dlv)'
Write-Output '============================================================'
Write-Output ''
cscript //nologo "$env:SystemRoot\System32\slmgr.vbs" /dlv *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] License detail query completed.'
Write-Output '============================================================'
"""

_ACT_ONLINE = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Online Activation (slmgr /ato)'
Write-Output '============================================================'
Write-Output ''
cscript //nologo "$env:SystemRoot\System32\slmgr.vbs" /ato *>&1 | Write-Output
Write-Output ''
Write-Output '[*] Verifying activation result...'
cscript //nologo "$env:SystemRoot\System32\slmgr.vbs" /xpr *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] Online activation attempt completed.'
Write-Output '============================================================'
"""

_ACT_KEY = r"""$key = '__INPUT__'
Write-Output '============================================================'
Write-Output ' SA WinTools - Install New Product Key (slmgr /ipk)'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Installing product key...'
cscript //nologo "$env:SystemRoot\System32\slmgr.vbs" /ipk $key *>&1 | Write-Output
Write-Output ''
Write-Output '[*] Attempting online activation...'
cscript //nologo "$env:SystemRoot\System32\slmgr.vbs" /ato *>&1 | Write-Output
Write-Output ''
Write-Output '[*] Verifying result...'
cscript //nologo "$env:SystemRoot\System32\slmgr.vbs" /xpr *>&1 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] Product key installation completed.'
Write-Output '============================================================'
"""

_WIFI_PROFILES = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Wi-Fi Saved Profiles'
Write-Output '============================================================'
Write-Output ''
netsh wlan show profiles *>&1 | Out-String -Width 4096 | Write-Output
Write-Output '[SUCCESS] Wi-Fi profiles query completed.'
Write-Output '============================================================'
"""

_WIFI_PASSWORD = r"""$profileName = '__INPUT__'
Write-Output '============================================================'
Write-Output " SA WinTools - Wi-Fi Password for: $profileName"
Write-Output '============================================================'
Write-Output ''
netsh wlan show profile name="$profileName" key=clear *>&1 | Out-String -Width 4096 | Write-Output
Write-Output '[SUCCESS] Wi-Fi password query completed.'
Write-Output '============================================================'
"""

_WIFI_REPORT = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Wi-Fi Connectivity Report'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Generating WLAN report (this may take a moment)...'
netsh wlan show wlanreport *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[INFO] Report saved to: C:\ProgramData\Microsoft\Windows\WlanReport\'
Write-Output '[SUCCESS] Wi-Fi report generated.'
Write-Output '============================================================'
"""

_FW_DISABLE = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Disable Windows Firewall (All Profiles)'
Write-Output '============================================================'
Write-Output ''
netsh advfirewall set allprofiles state off *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[WARNING] Firewall is now DISABLED on all profiles.'
Write-Output '[!] Re-enable immediately using Enable Firewall mode.'
Write-Output '============================================================'
"""

_FW_ENABLE = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Enable Windows Firewall (All Profiles)'
Write-Output '============================================================'
Write-Output ''
netsh advfirewall set allprofiles state on *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] Firewall re-enabled on all profiles.'
Write-Output '============================================================'
"""

_ENERGY_REPORT = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Energy Efficiency Report (powercfg /energy)'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Generating energy report - this takes approximately 60 seconds...'
$reportPath = "$env:TEMP\energy-report.html"
powercfg /energy /output "$reportPath" *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
if (Test-Path $reportPath) {
    Write-Output "[INFO] Report saved to: $reportPath"
    Write-Output '[*] Opening report in default browser...'
    Start-Process $reportPath
}
Write-Output '[SUCCESS] Energy report completed.'
Write-Output '============================================================'
"""

_BATTERY_REPORT = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Battery Health Report (powercfg /batteryreport)'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Generating battery report...'
$reportPath = "$env:TEMP\battery-report.html"
powercfg /batteryreport /output "$reportPath" *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
if (Test-Path $reportPath) {
    Write-Output "[INFO] Report saved to: $reportPath"
    Write-Output '[*] Opening report in default browser...'
    Start-Process $reportPath
}
Write-Output '[SUCCESS] Battery report completed.'
Write-Output '============================================================'
"""

_AUTOPILOT_HASH = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Export Autopilot Hardware Hash'
Write-Output '============================================================'
Write-Output ''
try {
    $serial = (Get-WmiObject Win32_BIOS).SerialNumber
    $productId = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').ProductId
    $hash = ''
    try {
        $obj = Get-WmiObject -Namespace root/cimv2/mdm/dmmap -Class MDM_DevDetail_Ext01 -ErrorAction Stop |
               Where-Object { $_.InstanceID -eq 'Ext' -and $_.ParentID -eq './DevDetail' }
        if ($obj -and $obj.DeviceHardwareData) {
            $hash = ($obj.DeviceHardwareData).Trim()
        }
    } catch {
        Write-Output "[!] Could not query hardware hash from WMI namespace root/cimv2/mdm/dmmap."
    }
    if ($hash) {
        $csv = "Device Serial Number,Windows Product ID,Hardware Hash`r`n"
        $csv += "$serial,$productId,$hash`r`n"
        $path = [System.IO.Path]::Combine($env:USERPROFILE, "Desktop", "AutopilotHWID.csv")
        [System.IO.File]::WriteAllText($path, $csv, [System.Text.Encoding]::UTF8)
        Write-Output "[SUCCESS] Autopilot CSV exported to: $path"
        Write-Output ''
        Write-Output "  Device Serial: $serial"
        Write-Output "  Product ID:    $productId"
        Write-Output "  Hardware Hash: $hash"
        Write-Output ''
        Write-Output '------------------------------------------------------------'
        Write-Output ' Validating hardware hash...'
        Write-Output '------------------------------------------------------------'
        $valid = $true
        $issues = @()

        if ($hash.Length -lt 1000) {
            $valid = $false
            $issues += "Hash too short ($($hash.Length) chars, expected ~4000)"
        } else {
            Write-Output "  [OK] Hash length: $($hash.Length) chars"
        }

        try {
            $decoded = [System.Convert]::FromBase64String($hash)
            Write-Output "  [OK] Base64 decodes to $($decoded.Length) bytes (expected 3000)"

            $sig = [System.Text.Encoding]::ASCII.GetString($decoded[0..2])
            if ($sig -ne 'OAM') {
                $valid = $false
                $issues += "Invalid signature '$sig' (expected 'OAM')"
            } else {
                Write-Output "  [OK] Signature: OAM (valid Autopilot hardware hash)"
            }

            $sb = New-Object System.Text.StringBuilder
            foreach ($b in $decoded) {
                if ($b -ge 32 -and $b -lt 127) {
                    [void]$sb.Append([char]$b)
                } else {
                    if ($sb.Length -ge 5) {
                        $s = $sb.ToString()
                        if ($s -match 'AMD|Intel|Samsung|WDC|TOSHIBA|ST[0-9]|WD-|NVMe|SSD|TPM|Megatrends|Micro-Star|ASUS|Gigabyte|Dell|HP|Lenovo|Ryzen|Core|Radeon|GeForce|Version|Serial|BIOS') {
                            Write-Output "  [OK] Embedded hardware: $s"
                        }
                    }
                    [void]$sb.Clear()
                }
            }
            if ($sb.Length -ge 5) {
                $s = $sb.ToString()
                if ($s -match 'AMD|Intel|Samsung|WDC|TOSHIBA|ST[0-9]|WD-|NVMe|SSD|TPM|Megatrends|Micro-Star|ASUS|Gigabyte|Dell|HP|Lenovo|Ryzen|Core|Radeon|GeForce|Version|Serial|BIOS') {
                    Write-Output "  [OK] Embedded hardware: $s"
                }
            }
        } catch {
            $valid = $false
            $issues += "Not valid Base64: $($_.Exception.Message)"
        }

        $csvContent = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::Default)
        $csvHash = ($csvContent -split "`r`n")[1].Split(',')[2]
        if ($csvHash -ne $hash) {
            $valid = $false
            $issues += "CSV hash does not match WMI source hash"
        } else {
            Write-Output "  [OK] CSV hash matches WMI source exactly"
        }

        if ($valid) {
            Write-Output ''
            Write-Output '[VALID] Hardware hash is correct and complete.'
            Write-Output '        Safe to import into Intune / Autopilot.'
        } else {
            Write-Output ''
            Write-Output '[INVALID] Hash validation failed:'
            foreach ($i in $issues) { Write-Output "  - $i" }
        }
    } else {
        Write-Output "[!] Hardware hash not available."
        Write-Output "    Ensure the device is MDM-enrolled or run 'mdmdiagnosticstool' first."
        Write-Output "    Serial: $serial  |  Product ID: $productId"
    }
} catch {
    Write-Output "[ERROR] $($_.Exception.Message)"
}
Write-Output '============================================================'
Write-Output ' Autopilot hardware hash export completed.'
Write-Output '============================================================'
"""


_MEM_DIAG_GUI = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Windows Memory Diagnostic GUI (mdsched)'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Launching Windows Memory Diagnostic scheduler GUI...'
$exe = "$env:SystemRoot\System32\MdSched.exe"
if (Test-Path $exe) {
    try {
        Start-Process -FilePath $exe -ErrorAction Stop
        Write-Output '[SUCCESS] Memory Diagnostic GUI launched.'
        Write-Output ''
        Write-Output '[TIP] Choose "Restart now" or "Check on next start" from the GUI.'
    } catch {
        Write-Output "[ERROR] Could not launch mdsched.exe: $($_.Exception.Message)"
    }
} else {
    Write-Output "[ERROR] mdsched.exe not found at: $exe"
}
Write-Output '============================================================'
"""

_MEM_DIAG_SCHEDULE = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Schedule Memory Diagnostic on Next Reboot'
Write-Output '============================================================'
Write-Output ''
$exe = "$env:SystemRoot\System32\MdSched.exe"
if (-not (Test-Path $exe)) {
    Write-Output "[ERROR] mdsched.exe not found at: $exe"
    Write-Output '============================================================'
    return
}
$runOnceKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce'
Write-Output '[*] Setting RunOnce key to trigger memory diagnostic on next boot...'
try {
    if (-not (Test-Path $runOnceKey)) {
        New-Item -Path $runOnceKey -Force | Out-Null
    }
    Set-ItemProperty -Path $runOnceKey -Name '!WindowsMemoryDiagnostic' -Value $exe -EA Stop
    Write-Output ''
    Write-Output '[SUCCESS] Memory Diagnostic scheduled for next reboot.'
    Write-Output '[!] Reboot your computer to start the diagnostic.'
    Write-Output '============================================================'
    Write-Output '[!] REBOOT REQUIRED for changes to take effect.'
    Write-Output '============================================================'
} catch {
    Write-Output "[ERROR] $($_.Exception.Message)"
    Write-Output '============================================================'
}
"""

_HOSTS_EDITOR = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Edit Hosts File in Notepad'
Write-Output '============================================================'
Write-Output ''
$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
Write-Output "[*] Hosts file path: $hostsPath"
if (-not (Test-Path $hostsPath)) {
    Write-Output "[ERROR] Hosts file not found."
    Write-Output '============================================================'
    return
}
$item = Get-Item $hostsPath -Force -EA 0
if ($item) {
    $sizeKB = [math]::Round($item.Length/1KB, 1)
    Write-Output "[*] Current size: $sizeKB KB"
}
Write-Output '[*] Opening in Notepad...'
try {
    Start-Process -FilePath 'notepad.exe' -ArgumentList $hostsPath -ErrorAction Stop
    Write-Output ''
    Write-Output '[SUCCESS] Hosts file opened in Notepad.'
    Write-Output '[TIP] Save changes in Notepad. No reboot needed for hosts changes.'
} catch {
    Write-Output "[ERROR] $($_.Exception.Message)"
}
Write-Output '============================================================'
"""

_WU_SCAN = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Trigger Windows Update Scan'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Triggering Windows Update scan (UsoClient StartScan)...'
$exe = "$env:SystemRoot\System32\usoclient.exe"
if (-not (Test-Path $exe)) {
    Write-Output "[ERROR] usoclient.exe not found at: $exe"
    Write-Output '        Windows 10 1709+ is required.'
    Write-Output '============================================================'
    return
}
try {
    Start-Process -FilePath $exe -ArgumentList 'StartScan' -NoNewWindow -Wait -EA Stop
    Write-Output ''
    Write-Output '[SUCCESS] Windows Update scan triggered.'
    Write-Output '[TIP] Open Settings > Update & Security to see results.'
} catch {
    Write-Output "[ERROR] $($_.Exception.Message)"
}
Write-Output '============================================================'
"""

_WU_INSTALL = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Trigger Windows Update Install'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Triggering Windows Update install (UsoClient StartInstall)...'
$exe = "$env:SystemRoot\System32\usoclient.exe"
if (-not (Test-Path $exe)) {
    Write-Output "[ERROR] usoclient.exe not found at: $exe"
    Write-Output '        Windows 10 1709+ is required.'
    Write-Output '============================================================'
    return
}
Write-Output '[!] This will download and install pending updates.'
try {
    Start-Process -FilePath $exe -ArgumentList 'StartInstall' -NoNewWindow -Wait -EA Stop
    Write-Output ''
    Write-Output '[SUCCESS] Windows Update install triggered.'
    Write-Output '[TIP] Some updates may require a reboot to complete.'
} catch {
    Write-Output "[ERROR] $($_.Exception.Message)"
}
Write-Output '============================================================'
"""


# ---------------------------------------------------------------------------
#  Disk Analyzer - path_select scan scripts (emit __SCAN_BEGIN__/__SCAN_END__
#  with `size_bytes\tpath` rows between the markers; the GUI parses them to
#  build a multi-select dialog). For Appx, the format is
#  `size_bytes\tfullname\tdisplay_name` (id_col=True).
# ---------------------------------------------------------------------------
_SCAN_APPDATA_LOCAL = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - AppData\Local Folder Scan (Top 20)'
Write-Output '============================================================'
Write-Output ''
Write-Output "[*] Scanning $env:LOCALAPPDATA ..."
Write-Output ''
$rows = Get-ChildItem -Path $env:LOCALAPPDATA -Directory -EA SilentlyContinue | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse -Force -File -EA SilentlyContinue |
             Measure-Object -Property Length -Sum).Sum
    if (-not $size) { $size = [long]0 }
    [PSCustomObject]@{
        SizeGB  = [math]::Round($size / 1GB, 2)
        SizeMB  = [math]::Round($size / 1MB, 1)
        Path    = $_.FullName
        SizeRaw = $size
    }
} | Sort-Object SizeRaw -Descending | Select-Object -First 20
if ($rows) {
    $rows | Select-Object SizeGB, SizeMB, Path |
        Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
} else {
    Write-Output '[INFO] No folders found.'
}
Write-Output ''
Write-Output '__SCAN_BEGIN__'
foreach ($r in $rows) { Write-Output "$($r.SizeRaw)`t$($r.Path)" }
Write-Output '__SCAN_END__'
Write-Output ''
Write-Output '[SUCCESS] AppData\Local scan completed.'
Write-Output '============================================================'
"""

_SCAN_APPDATA_ROAMING = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - AppData\Roaming Folder Scan (Top 20)'
Write-Output '============================================================'
Write-Output ''
Write-Output "[*] Scanning $env:APPDATA ..."
Write-Output ''
$rows = Get-ChildItem -Path $env:APPDATA -Directory -EA SilentlyContinue | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse -Force -File -EA SilentlyContinue |
             Measure-Object -Property Length -Sum).Sum
    if (-not $size) { $size = [long]0 }
    [PSCustomObject]@{
        SizeGB  = [math]::Round($size / 1GB, 2)
        SizeMB  = [math]::Round($size / 1MB, 1)
        Path    = $_.FullName
        SizeRaw = $size
    }
} | Sort-Object SizeRaw -Descending | Select-Object -First 20
if ($rows) {
    $rows | Select-Object SizeGB, SizeMB, Path |
        Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
} else {
    Write-Output '[INFO] No folders found.'
}
Write-Output ''
Write-Output '__SCAN_BEGIN__'
foreach ($r in $rows) { Write-Output "$($r.SizeRaw)`t$($r.Path)" }
Write-Output '__SCAN_END__'
Write-Output ''
Write-Output '[SUCCESS] AppData\Roaming scan completed.'
Write-Output '============================================================'
"""

_SCAN_PROFILE_FILES = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Profile Files Scan (Top 20)'
Write-Output '============================================================'
Write-Output ''
Write-Output "[*] Scanning $env:USERPROFILE for the biggest files..."
Write-Output ''
$rows = Get-ChildItem -Path $env:USERPROFILE -Recurse -File -Force -EA SilentlyContinue |
    Sort-Object Length -Descending |
    Select-Object -First 20 |
    ForEach-Object {
        [PSCustomObject]@{
            SizeGB  = [math]::Round($_.Length / 1GB, 2)
            SizeMB  = [math]::Round($_.Length / 1MB, 1)
            Path    = $_.FullName
            SizeRaw = $_.Length
        }
    }
if ($rows) {
    $rows | Select-Object SizeGB, SizeMB, Path |
        Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
} else {
    Write-Output '[INFO] No files found.'
}
Write-Output ''
Write-Output '__SCAN_BEGIN__'
foreach ($r in $rows) { Write-Output "$($r.SizeRaw)`t$($r.Path)" }
Write-Output '__SCAN_END__'
Write-Output ''
Write-Output '[SUCCESS] Profile files scan completed.'
Write-Output '============================================================'
"""

_SCAN_APPX = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Appx Package Scan (Top 20 by Size)'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Enumerating Appx packages for all users...'
Write-Output ''
$rows = Get-AppxPackage -AllUsers -EA SilentlyContinue | Where-Object { $_.InstallLocation } | ForEach-Object {
    $path = $_.InstallLocation
    $size = [long]0
    if (Test-Path $path) {
        $s = (Get-ChildItem -Path $path -Recurse -Force -File -EA SilentlyContinue |
              Measure-Object -Property Length -Sum).Sum
        if ($s) { $size = [long]$s }
    }
    [PSCustomObject]@{
        SizeMB    = [math]::Round($size / 1MB, 1)
        Name      = $_.Name
        FullName  = $_.PackageFullName
        SizeRaw   = $size
    }
} | Sort-Object SizeRaw -Descending | Select-Object -First 20
if ($rows) {
    $rows | Select-Object SizeMB, Name, FullName |
        Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
} else {
    Write-Output '[INFO] No Appx packages with an install location found.'
}
Write-Output ''
Write-Output '__SCAN_BEGIN__'
foreach ($r in $rows) { Write-Output "$($r.SizeRaw)`t$($r.FullName)`t$($r.Name)" }
Write-Output '__SCAN_END__'
Write-Output ''
Write-Output '[SUCCESS] Appx scan completed.'
Write-Output '============================================================'
"""

_DELETE_PATHS = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Delete Selected Paths'
Write-Output '============================================================'
Write-Output ''
$paths = @'
__PATHS__
'@ -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
if (-not $paths) {
    Write-Output '[ERROR] No paths supplied.'
    Write-Output '============================================================'
    return
}
Write-Output "[*] Processing $($paths.Count) path(s)..."
Write-Output ''
$totalReclaimed = [long]0
$ok = 0
$failed = 0
$skipped = 0
foreach ($p in $paths) {
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Output "[SKIP] Not found: $p"
        $skipped++
        continue
    }
    try {
        $item = Get-Item -LiteralPath $p -Force -EA Stop
        if ($item.PSIsContainer) {
            $size = (Get-ChildItem -LiteralPath $p -Recurse -Force -File -EA 0 |
                     Measure-Object -Property Length -Sum).Sum
        } else {
            $size = $item.Length
        }
        if (-not $size) { $size = [long]0 }
        Remove-Item -LiteralPath $p -Recurse -Force -EA Stop
        $mb = [math]::Round($size / 1MB, 1)
        Write-Output "[OK] Removed: $p ($mb MB)"
        $totalReclaimed += $size
        $ok++
    } catch {
        Write-Output "[!] Failed: $p - $($_.Exception.Message)"
        $failed++
    }
}
Write-Output ''
Write-Output '======================================='
Write-Output ' DELETE SUMMARY'
Write-Output '======================================='
Write-Output "  Removed       : $ok"
Write-Output "  Failed        : $failed"
Write-Output "  Not found     : $skipped"
Write-Output "  Reclaimed     : $([math]::Round($totalReclaimed / 1MB, 1)) MB ($([math]::Round($totalReclaimed / 1GB, 2)) GB)"
Write-Output '======================================='
Write-Output '[SUCCESS] Path deletion completed.'
Write-Output '============================================================'
"""

_REMOVE_APPX = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Remove Selected Appx Packages'
Write-Output '============================================================'
Write-Output ''
$pkgs = @'
__PATHS__
'@ -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
if (-not $pkgs) {
    Write-Output '[ERROR] No packages supplied.'
    Write-Output '============================================================'
    return
}
Write-Output "[*] Removing $($pkgs.Count) Appx package(s)..."
Write-Output ''
$ok = 0
$failed = 0
foreach ($pkg in $pkgs) {
    try {
        Remove-AppxPackage -Package $pkg -AllUsers -EA Stop
        Write-Output "[OK] Removed: $pkg"
        $ok++
    } catch {
        Write-Output "[!] Failed: $pkg - $($_.Exception.Message)"
        $failed++
    }
}
Write-Output ''
Write-Output '======================================='
Write-Output ' APPX REMOVAL SUMMARY'
Write-Output '======================================='
Write-Output "  Removed : $ok"
Write-Output "  Failed  : $failed"
Write-Output '======================================='
Write-Output '[SUCCESS] Appx removal completed.'
Write-Output '============================================================'
"""


# ---------------------------------------------------------------------------
#  Dev cache cleaner scripts
# ---------------------------------------------------------------------------
_NPM_CACHE_CLEAN = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - npm Cache Clean'
Write-Output '============================================================'
Write-Output ''
$npm = Get-Command npm -EA SilentlyContinue
if (-not $npm) {
    Write-Output '[INFO] npm not found on PATH - nothing to clean.'
    Write-Output '============================================================'
    return
}
Write-Output '[*] Running: npm cache clean --force'
Write-Output ''
& npm cache clean --force *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] npm cache cleaned.'
Write-Output '============================================================'
"""

_PIP_CACHE_PURGE = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - pip Cache Purge'
Write-Output '============================================================'
Write-Output ''
$pip = Get-Command pip -EA SilentlyContinue
if (-not $pip) {
    Write-Output '[INFO] pip not found on PATH - nothing to clean.'
    Write-Output '============================================================'
    return
}
Write-Output '[*] Running: pip cache purge'
Write-Output ''
& pip cache purge *>&1 | Out-String -Width 4096 | Write-Output
Write-Output ''
Write-Output '[SUCCESS] pip cache purged.'
Write-Output '============================================================'
"""

_REMOVE_UV_CACHE = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Remove uv Cache'
Write-Output '============================================================'
Write-Output ''
$target = "$env:LOCALAPPDATA\uv"
if (-not (Test-Path $target)) {
    Write-Output "[INFO] Not found - nothing to clean: $target"
    Write-Output '============================================================'
    return
}
$size = (Get-ChildItem $target -Recurse -Force -File -EA SilentlyContinue |
         Measure-Object -Property Length -Sum).Sum
if (-not $size) { $size = [long]0 }
$mb = [math]::Round($size / 1MB, 1)
Write-Output "[*] Removing: $target ($mb MB)"
try {
    Remove-Item $target -Recurse -Force -EA Stop
    Write-Output "[OK] Removed ($mb MB reclaimed)."
} catch {
    Write-Output "[!] Failed: $($_.Exception.Message)"
}
Write-Output ''
Write-Output '[SUCCESS] uv cache removal completed.'
Write-Output '============================================================'
"""

_REMOVE_LMSTUDIO_UPDATER = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Remove LM Studio Updater'
Write-Output '============================================================'
Write-Output ''
$target = "$env:LOCALAPPDATA\lm-studio-updater"
if (-not (Test-Path $target)) {
    Write-Output "[INFO] Not found - nothing to clean: $target"
    Write-Output '============================================================'
    return
}
$size = (Get-ChildItem $target -Recurse -Force -File -EA SilentlyContinue |
         Measure-Object -Property Length -Sum).Sum
if (-not $size) { $size = [long]0 }
$mb = [math]::Round($size / 1MB, 1)
Write-Output "[*] Removing: $target ($mb MB)"
try {
    Remove-Item $target -Recurse -Force -EA Stop
    Write-Output "[OK] Removed ($mb MB reclaimed)."
} catch {
    Write-Output "[!] Failed: $($_.Exception.Message)"
}
Write-Output ''
Write-Output '[SUCCESS] LM Studio updater removal completed.'
Write-Output '============================================================'
"""

_REMOVE_VORTEX_UPDATER = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Remove Vortex Updater'
Write-Output '============================================================'
Write-Output ''
$target = "$env:LOCALAPPDATA\vortex-updater"
if (-not (Test-Path $target)) {
    Write-Output "[INFO] Not found - nothing to clean: $target"
    Write-Output '============================================================'
    return
}
$size = (Get-ChildItem $target -Recurse -Force -File -EA SilentlyContinue |
         Measure-Object -Property Length -Sum).Sum
if (-not $size) { $size = [long]0 }
$mb = [math]::Round($size / 1MB, 1)
Write-Output "[*] Removing: $target ($mb MB)"
try {
    Remove-Item $target -Recurse -Force -EA Stop
    Write-Output "[OK] Removed ($mb MB reclaimed)."
} catch {
    Write-Output "[!] Failed: $($_.Exception.Message)"
}
Write-Output ''
Write-Output '[SUCCESS] Vortex updater removal completed.'
Write-Output '============================================================'
"""

_REMOVE_RSI_UPDATER = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Remove RSI Launcher Updater'
Write-Output '============================================================'
Write-Output ''
$target = "$env:LOCALAPPDATA\rsilauncher-updater"
if (-not (Test-Path $target)) {
    Write-Output "[INFO] Not found - nothing to clean: $target"
    Write-Output '============================================================'
    return
}
$size = (Get-ChildItem $target -Recurse -Force -File -EA SilentlyContinue |
         Measure-Object -Property Length -Sum).Sum
if (-not $size) { $size = [long]0 }
$mb = [math]::Round($size / 1MB, 1)
Write-Output "[*] Removing: $target ($mb MB)"
try {
    Remove-Item $target -Recurse -Force -EA Stop
    Write-Output "[OK] Removed ($mb MB reclaimed)."
} catch {
    Write-Output "[!] Failed: $($_.Exception.Message)"
}
Write-Output ''
Write-Output '[SUCCESS] RSI Launcher updater removal completed.'
Write-Output '============================================================'
"""


# ---------------------------------------------------------------------------
#  Hibernate manager scripts
# ---------------------------------------------------------------------------
_HIBERNATE_OFF = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Disable Hibernation'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Current hibernation status:'
$before = powercfg /a *>&1 | Out-String -Width 4096
Write-Output $before
Write-Output ''
if ($before -match 'Hibernation has been disabled by the|Hibernation is not available|The following sleep states are not available') {
    Write-Output '[INFO] Hibernation appears already disabled or unavailable.'
    Write-Output '============================================================'
    return
}
Write-Output '[*] Disabling hibernation (powercfg /hibernate off)...'
powercfg /hibernate off *>&1 | Write-Output
Write-Output ''
Write-Output '[*] Re-checking status...'
$after = powercfg /a *>&1 | Out-String -Width 4096
Write-Output $after
Write-Output ''
Write-Output '[SUCCESS] Hibernation disable attempted. hiberfil.sys will be removed on next boot.'
Write-Output '============================================================'
"""

_HIBERNATE_ON = r"""Write-Output '============================================================'
Write-Output ' SA WinTools - Enable Hibernation'
Write-Output '============================================================'
Write-Output ''
Write-Output '[*] Current hibernation status:'
$before = powercfg /a *>&1 | Out-String -Width 4096
Write-Output $before
Write-Output ''
if ($before -match 'Hibernation Timeout|Standby \(S3\)|Hibernate -|^Hibernation ') {
    Write-Output '[INFO] Hibernation appears already available.'
    Write-Output '============================================================'
    return
}
Write-Output '[*] Enabling hibernation (powercfg /hibernate on)...'
powercfg /hibernate on *>&1 | Write-Output
Write-Output ''
Write-Output '[*] Re-checking status...'
$after = powercfg /a *>&1 | Out-String -Width 4096
Write-Output $after
Write-Output ''
Write-Output '[SUCCESS] Hibernation enable attempted. hiberfil.sys will be created on next boot.'
Write-Output '============================================================'
"""


# ---------------------------------------------------------------------------
#  Tool catalogue
# ---------------------------------------------------------------------------
# Each category has a colour key (mapped to a QSS accent in gui.py).
# Each tool has a list of modes; a mode may carry:
#   confirm : show a Yes/No confirmation dialog before running
#   reboot  : show a "reboot required" status notice after running
#   input   : {"type": "text"|"drive"|"hdd_check"|"path_select", ...}
#             collected before run. path_select is a two-phase scan-then-pick
#             flow: it carries a scan_script + script with __PATHS__ token.
CATEGORIES: list[dict] = [
    {
        "key": "repair",
        "name": "System Repair",
        "desc": "Active repair & fix operations (escalating depth).",
        "tools": [
            {
                "name": "SFC Repair",
                "desc": "Scans Windows files for damage and repairs them automatically.",
                "modes": [{"label": "Run sfc /scannow", "script": _SFC}],
            },
            {
                "name": "DISM Clean",
                "desc": "Clears leftover Windows update data to free up disk space.",
                "modes": [{"label": "Run /StartComponentCleanup /ResetBase", "script": _DISM_CLEAN}],
            },
            {
                "name": "DISM Repair",
                "desc": "Downloads fresh Windows files from Microsoft to fix deep system issues.",
                "modes": [{"label": "Run /RestoreHealth", "script": _DISM_REPAIR}],
            },
            {
                "name": "Fix Win Update",
                "desc": "Unsticks Windows Update when it stops working or gets stuck.",
                "modes": [{"label": "Run full fix sequence", "script": _FIX_WINUPDATE}],
            },
            {
                "name": "WinRE Manager",
                "desc": "Checks that Windows Recovery mode is ready for emergency use.",
                "modes": [{"label": "Check & enable WinRE", "script": _WINRE}],
            },
        ],
    },
    {
        "key": "maintenance",
        "name": "Maintenance",
        "desc": "Cleanup, disk analysis, and queue/print repairs.",
        "tools": [
            {
                "name": "Cleanup",
                "desc": "Deletes junk files, temp data, and old logs to recover disk space.",
                "modes": [{"label": "Run 16-target cleanup", "script": _CLEANUP, "confirm": True}],
            },
            {
                "name": "Disk Analyzer",
                "desc": "Finds large files, biggest folders, duplicates; pick which to delete.",
                "modes": [
                    {"label": "Large Files > 500 MB...", "script": _DISK_LARGE_FILES,
                     "input": {"type": "drive", "label": "Select drive to scan for large files:"}},
                    {"label": "Top 50 Biggest Files...", "script": _DISK_TOP_FILES,
                     "input": {"type": "drive", "label": "Select drive to scan for biggest files:"}},
                    {"label": "Top 10 Largest Folders...", "script": _DISK_TOP_FOLDERS,
                     "input": {"type": "drive", "label": "Select drive to scan for top folders:"}},
                    {"label": "Folder Size Map (recursive)...", "script": _DISK_FOLDER_MAP,
                     "input": {"type": "drive", "label": "Select drive to map (top 20 by size):"}},
                    {"label": "Duplicate File Finder...", "script": _DISK_DUPLICATES,
                     "input": {"type": "drive", "label": "Select drive to scan for duplicate files:"}},
                    {"label": "AppData\\Local - Top 20 Folders...",
                     "input": {"type": "path_select",
                               "label": "Select AppData\\Local folders to delete:",
                               "scan_script": _SCAN_APPDATA_LOCAL,
                               "script": _DELETE_PATHS,
                               "blocklist": True},
                     "confirm": True},
                    {"label": "AppData\\Roaming - Top 20 Folders...",
                     "input": {"type": "path_select",
                               "label": "Select AppData\\Roaming folders to delete:",
                               "scan_script": _SCAN_APPDATA_ROAMING,
                               "script": _DELETE_PATHS,
                               "blocklist": True},
                     "confirm": True},
                    {"label": "Profile - Top 20 Files...",
                     "input": {"type": "path_select",
                               "label": "Select user profile files to delete:",
                               "scan_script": _SCAN_PROFILE_FILES,
                               "script": _DELETE_PATHS,
                               "blocklist": True},
                     "confirm": True},
                ],
            },
            {
                "name": "Appx Manager",
                "desc": "Lists installed Appx packages by size, lets you pick which to uninstall.",
                "modes": [
                    {"label": "Uninstall Appx Packages (Top 20 by Size)...",
                     "input": {"type": "path_select",
                               "label": "Select Appx packages to uninstall:",
                               "scan_script": _SCAN_APPX,
                               "script": _REMOVE_APPX,
                               "id_col": True,
                               "blocklist": False},
                     "confirm": True},
                ],
            },
            {
                "name": "Dev Cache Cleaner",
                "desc": "Clears package manager caches and removes leftover updater folders.",
                "modes": [
                    {"label": "npm cache clean --force", "script": _NPM_CACHE_CLEAN, "confirm": True},
                    {"label": "pip cache purge", "script": _PIP_CACHE_PURGE, "confirm": True},
                    {"label": "Remove uv cache", "script": _REMOVE_UV_CACHE, "confirm": True},
                    {"label": "Remove LM Studio Updater", "script": _REMOVE_LMSTUDIO_UPDATER, "confirm": True},
                    {"label": "Remove Vortex Updater", "script": _REMOVE_VORTEX_UPDATER, "confirm": True},
                    {"label": "Remove RSI Launcher Updater", "script": _REMOVE_RSI_UPDATER, "confirm": True},
                ],
            },
            {
                "name": "Hibernate Manager",
                "desc": "Toggles Windows hibernation to free up or restore hiberfil.sys (often 6-16 GB).",
                "modes": [
                    {"label": "Disable Hibernation (free hiberfil.sys)", "script": _HIBERNATE_OFF, "confirm": True},
                    {"label": "Enable Hibernation", "script": _HIBERNATE_ON},
                ],
            },
            {
                "name": "Reset Spooler",
                "desc": "Fixes print queue problems by restarting the print service.",
                "modes": [{"label": "Stop / clear / start spooler", "script": _RESET_SPOOLER}],
            },
            {
                "name": "Install/Uninstall",
                "desc": "Scans and repairs broken entries stopping programs from installing.",
                "modes": [
                    {"label": "Scan (read-only)", "script": _INSTALL_SCAN},
                    {"label": "Fix (backup + repair)", "script": _INSTALL_FIX, "confirm": True},
                ],
            },
            {
                "name": "Flush Network",
                "desc": "Resets DNS cache, network settings, or IP config to fix connectivity.",
                "modes": [
                    {"label": "Flush DNS", "script": _FLUSH_DNS},
                    {"label": "Winsock Reset", "script": _WINSOCK_RESET, "reboot": True},
                    {"label": "IP Reset", "script": _IP_RESET, "reboot": True},
                    {"label": "Release IP", "script": _RELEASE_IP},
                    {"label": "Renew IP", "script": _RENEW_IP},
                    {"label": "Reset Network Credentials", "script": _RESET_NET_CREDS, "confirm": True},
                ],
            },
        ],
    },
    {
        "key": "diagnostics",
        "name": "Hardware & Diagnostics",
        "desc": "Disk health, device queries, and services.",
        "tools": [
            {
                "name": "Trim SSD",
                "desc": "Tells your SSD to clean up internally, keeping it fast and healthy.",
                "modes": [{"label": "Auto-detect & trim all SSD volumes", "script": _TRIM_SSD}],
            },
            {
                "name": "Check HDD",
                "desc": "Scans a hard drive for errors or schedules a repair on next startup.",
                "modes": [{
                    "label": "Select drive & chkdsk mode...",
                    "script": _CHECK_HDD,
                    "input": {"type": "hdd_check"},
                }],
            },
            {
                "name": "Device Query",
                "desc": "Lists HID devices, removes problem entries, or resets Bluetooth adapters.",
                "modes": [
                    {"label": "HID Device Services", "script": _HID_SERVICES},
                    {"label": "Remove HID Errors", "script": _REMOVE_HID_ERRORS},
                    {"label": "Reset Bluetooth Adapter", "script": _BT_RESET, "confirm": True},
                ],
            },
            {
                "name": "Services Check",
                "desc": "Finds and restarts services set to run automatically that have stopped.",
                "modes": [
                    {"label": "Restart All Stopped Auto-Start", "script": _SVC_RESTART, "confirm": True},
                ],
            },
            {
                "name": "Memory Diagnostic",
                "desc": "Runs Windows Memory Diagnostic to detect RAM hardware errors.",
                "modes": [
                    {"label": "Open Memory Diagnostic GUI", "script": _MEM_DIAG_GUI},
                    {"label": "Schedule on Next Reboot", "script": _MEM_DIAG_SCHEDULE, "reboot": True},
                ],
            },
        ],
    },
    {
        "key": "status",
        "name": "System Info & Status",
        "desc": "Time sync, activation, Wi-Fi, firewall, and system reports.",
        "tools": [
            {
                "name": "Time Sync",
                "desc": "Checks or forces Windows to sync its clock with the internet time server.",
                "modes": [
                    {"label": "Check Time Status", "script": _TIME_STATUS},
                    {"label": "Force Resync", "script": _TIME_RESYNC},
                    {"label": "Re-register Time Service", "script": _TIME_REREGISTER},
                ],
            },
            {
                "name": "Activation",
                "desc": "Shows full license info, reactivates online, or installs a new product key.",
                "modes": [
                    {"label": "Full License Info (slmgr /dlv)", "script": _ACT_DETAIL},
                    {"label": "Activate Online (slmgr /ato)", "script": _ACT_ONLINE},
                    {"label": "Enter New Product Key...", "script": _ACT_KEY,
                     "confirm": True,
                     "input": {"type": "text", "label": "Product Key (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX):",
                               "placeholder": "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX", "maxlen": 29}},
                ],
            },
            {
                "name": "Wi-Fi",
                "desc": "Shows Wi-Fi profiles and passwords, generates WLAN report.",
                "modes": [
                    {"label": "Wi-Fi Profiles", "script": _WIFI_PROFILES},
                    {"label": "Wi-Fi Password...", "script": _WIFI_PASSWORD,
                     "input": {"type": "text", "label": "Wi-Fi Profile Name (exact, case-sensitive):",
                               "placeholder": "MyNetwork", "maxlen": 100}},
                    {"label": "Wi-Fi Report", "script": _WIFI_REPORT},
                ],
            },
            {
                "name": "Firewall",
                "desc": "Enable or disable the Windows Firewall on all profiles.",
                "modes": [
                    {"label": "Disable Firewall", "script": _FW_DISABLE, "confirm": True},
                    {"label": "Enable Firewall", "script": _FW_ENABLE},
                ],
            },
            {
                "name": "Power & System",
                "desc": "Generates energy efficiency or battery health reports.",
                "modes": [
                    {"label": "Energy Report (powercfg /energy)", "script": _ENERGY_REPORT},
                    {"label": "Battery Report (powercfg /batteryreport)", "script": _BATTERY_REPORT},
                ],
            },
            {
                "name": "Autopilot Hash",
                "desc": "Exports the Windows Autopilot hardware hash to a CSV for Intune enrollment.",
                "modes": [{"label": "Export to Desktop\\AutopilotHWID.csv", "script": _AUTOPILOT_HASH}],
            },
            {
                "name": "Hosts File Editor",
                "desc": "Opens the Windows hosts file in Notepad for manual editing.",
                "modes": [{"label": "Open hosts in Notepad", "script": _HOSTS_EDITOR}],
            },
            {
                "name": "Windows Update",
                "desc": "Triggers a Windows Update scan or install on demand.",
                "modes": [
                    {"label": "Start Scan", "script": _WU_SCAN},
                    {"label": "Start Install", "script": _WU_INSTALL},
                ],
            },
        ],
    },
]


def resolve_placeholders(script: str) -> str:
    """Substitute the non-input placeholders (lib path, backup root).

    Input-dependent placeholders (``__DRIVE__`` / ``__MODE__`` /
    ``__INPUT__``) are substituted by the GUI just before running, after it
    has collected the user's input.
    """
    return script.replace("__LIB__", LIB_PATH).replace("__BACKUP__", BACKUP_ROOT)
