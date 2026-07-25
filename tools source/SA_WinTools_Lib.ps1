# =====================================================================
# SA WinTools Professional v20.9 - Shared Function Library
# Copyright (c) 2026 - Antoniou Stavros. AI-Assisted Development.
# Dot-source this file: . .\SA_WinTools_Lib.ps1
# Works both in main GUI thread and inside Start-Job scriptblocks
# =====================================================================

# ---------------------------------------------------------------------
# UTILITY: Smart UninstallString Path Validator
# Returns: object with .IsBroken, .IsUnavailable, .CleanPath, .Reason
# Safety: Distinguishes genuinely broken paths from offline/network/
#         removable drives that are temporarily unavailable
# ---------------------------------------------------------------------
function Test-UninstallPath {
    param([string]$RawUninstallString)

    $result = [PSCustomObject]@{
        IsBroken      = $false
        IsUnavailable = $false
        CleanPath     = ""
        Reason        = "OK"
    }

    if ([string]::IsNullOrWhiteSpace($RawUninstallString)) {
        $result.IsBroken = $true
        $result.Reason   = "Empty UninstallString"
        return $result
    }

    $raw = $RawUninstallString.Trim()

    # MsiExec calls are always valid (Windows Installer engine handles them)
    if ($raw -match '(?i)^msiexec') {
        $result.Reason = "MSI-based (always valid)"
        return $result
    }
    # rundll32 calls are system-level, always valid
    if ($raw -match '(?i)^rundll32') {
        $result.Reason = "rundll32-based (always valid)"
        return $result
    }
    # cmd /c wrappers are too complex to parse reliably - skip
    if ($raw -match '(?i)^cmd\s') {
        $result.Reason = "cmd-wrapper (skipped)"
        return $result
    }

    # Extract the executable path
    $cleanPath = ""
    if ($raw -match '^"([^"]+)"') {
        $cleanPath = $Matches[1]
    } else {
        $cleanPath = ($raw -split '\s+[-/]')[0].Trim()
    }
    $result.CleanPath = $cleanPath

    if ([string]::IsNullOrWhiteSpace($cleanPath)) {
        $result.IsBroken = $true
        $result.Reason   = "Could not parse executable path"
        return $result
    }

    # Local drive path (C:\, D:\, etc.)
    if ($cleanPath -match '^([A-Za-z]):\\') {
        $driveRoot = "$($Matches[1]):\"
        if (-not (Test-Path $driveRoot)) {
            $result.IsUnavailable = $true
            $result.Reason = "Drive $driveRoot not available (removable/external?)"
            return $result
        }
        if (-not (Test-Path $cleanPath -EA 0)) {
            $result.IsBroken = $true
            $result.Reason   = "File not found: $cleanPath"
            return $result
        }
    }
    # UNC / network paths
    elseif ($cleanPath -match '^\\\\') {
        $result.IsUnavailable = $true
        $result.Reason = "Network path (cannot verify offline)"
        return $result
    }

    return $result
}

# ---------------------------------------------------------------------
# UTILITY: Classify a single uninstall registry key
# Returns: "ORPHAN_HIGH", "ORPHAN_MEDIUM", "BROKEN", "UNAVAILABLE",
#          "CLEAN", or "SYSTEM" (skipped)
# ---------------------------------------------------------------------
function Get-UninstallKeyStatus {
    param([string]$KeyPSPath)

    $props           = Get-ItemProperty $KeyPSPath -EA 0
    $displayName     = $props.DisplayName
    $uninstallStr    = $props.UninstallString
    $quietUninstall  = $props.QuietUninstallString

    # Skip system components
    if ($props.SystemComponent -eq 1) {
        return [PSCustomObject]@{ Status="SYSTEM"; DisplayName=$displayName; Reason="SystemComponent=1" }
    }

    # Check: Missing DisplayName
    if ([string]::IsNullOrWhiteSpace($displayName)) {
        $meaningfulProps = ($props.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' }).Name |
            Where-Object { $_ -notin @('PSPath','PSParentPath','PSChildName','PSProvider','PSDrive') }
        $confidence = if ($meaningfulProps.Count -le 1) { "HIGH" } else { "MEDIUM" }
        return [PSCustomObject]@{
            Status      = "ORPHAN_$confidence"
            DisplayName = $null
            Reason      = "Missing DisplayName ($($meaningfulProps.Count) properties)"
        }
    }

    # Check: UninstallString path validity
    $effectiveUninstall = if (-not [string]::IsNullOrWhiteSpace($uninstallStr)) { $uninstallStr }
        elseif (-not [string]::IsNullOrWhiteSpace($quietUninstall)) { $quietUninstall }
        else { $null }

    if ($null -ne $effectiveUninstall) {
        $pathCheck = Test-UninstallPath -RawUninstallString $effectiveUninstall
        if ($pathCheck.IsBroken) {
            return [PSCustomObject]@{
                Status      = "BROKEN"
                DisplayName = $displayName
                UninstallStr = $effectiveUninstall
                Reason      = $pathCheck.Reason
            }
        }
        if ($pathCheck.IsUnavailable) {
            return [PSCustomObject]@{
                Status      = "UNAVAILABLE"
                DisplayName = $displayName
                UninstallStr = $effectiveUninstall
                Reason      = $pathCheck.Reason
            }
        }
    }
    elseif ([string]::IsNullOrWhiteSpace($uninstallStr) -and [string]::IsNullOrWhiteSpace($quietUninstall)) {
        # No uninstall string at all - only flag if not a Windows Installer product
        if ($props.WindowsInstaller -ne 1) {
            return [PSCustomObject]@{
                Status      = "BROKEN"
                DisplayName = $displayName
                UninstallStr = "(none)"
                Reason      = "No UninstallString or QuietUninstallString"
            }
        }
    }

    return [PSCustomObject]@{ Status="CLEAN"; DisplayName=$displayName; Reason="OK" }
}

# ---------------------------------------------------------------------
# CORE: Full diagnostic scan (read-only, zero writes)
# Called by both the Scan button and the Fix button (pre-repair pass)
# Returns: hashtable with all classified results
# ---------------------------------------------------------------------
function Invoke-InstallScan {

    $uninstallPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKCU:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    )

    $totalScanned     = 0
    $orphanedHigh     = @()
    $orphanedMedium   = @()
    $brokenEntries    = @()
    $unavailEntries   = @()
    $duplicateMap     = @{}
    $duplicateEntries = @()

    # --- Scan Uninstall hives ---
    foreach ($regPath in $uninstallPaths) {
        if (-not (Test-Path $regPath)) {
            continue
        }
        $subKeys = Get-ChildItem $regPath -EA 0

        foreach ($key in $subKeys) {
            $totalScanned++
            $keyName = $key.PSChildName
            $status  = Get-UninstallKeyStatus -KeyPSPath $key.PSPath

            switch -Wildcard ($status.Status) {
                "SYSTEM"        { continue }
                "ORPHAN_HIGH"   {
                    $orphanedHigh += [PSCustomObject]@{
                        Path=$key.PSPath; KeyName=$keyName; HivePath=$regPath; Reason=$status.Reason
                    }
                }
                "ORPHAN_MEDIUM" {
                    $orphanedMedium += [PSCustomObject]@{
                        Path=$key.PSPath; KeyName=$keyName; HivePath=$regPath; Reason=$status.Reason
                    }
                }
                "BROKEN"        {
                    $brokenEntries += [PSCustomObject]@{
                        Path=$key.PSPath; KeyName=$keyName; HivePath=$regPath
                        DisplayName=$status.DisplayName; UninstallStr=$status.UninstallStr; Reason=$status.Reason
                    }
                }
                "UNAVAILABLE"   {
                    $unavailEntries += [PSCustomObject]@{
                        Path=$key.PSPath; KeyName=$keyName; DisplayName=$status.DisplayName; Reason=$status.Reason
                    }
                }
                "CLEAN"         {
                    # Track duplicates (clean entries only)
                    if (-not [string]::IsNullOrWhiteSpace($status.DisplayName)) {
                        $norm = $status.DisplayName.Trim().ToLower()
                        if ($duplicateMap.ContainsKey($norm)) { $duplicateMap[$norm] += @($key.PSPath) }
                        else { $duplicateMap[$norm] = @($key.PSPath) }
                    }
                }
            }
        }
    }

    # Resolve duplicates
    foreach ($name in $duplicateMap.Keys) {
        if ($duplicateMap[$name].Count -gt 1) {
            $duplicateEntries += [PSCustomObject]@{
                DisplayName=$name; Count=$duplicateMap[$name].Count; Paths=$duplicateMap[$name]
            }
        }
    }

    # --- Scan MSI Installer Products ---
    $msiProductPath  = "HKLM:\SOFTWARE\Classes\Installer\Products"
    $staleMsiEntries = @()
    $msiScanned      = 0

    if (Test-Path $msiProductPath) {
        $msiKeys = Get-ChildItem $msiProductPath -EA 0

        # Build GUID lookup from all uninstall hives
        $knownGuids = @{}
        foreach ($rp in $uninstallPaths) {
            if (Test-Path $rp) {
                Get-ChildItem $rp -EA 0 | ForEach-Object { $knownGuids[$_.PSChildName] = $true }
            }
        }

        foreach ($msiKey in $msiKeys) {
            $msiScanned++
            $msiProps    = Get-ItemProperty $msiKey.PSPath -EA 0
            $productCode = $msiKey.PSChildName
            $matchFound  = $knownGuids.ContainsKey($productCode) -or $knownGuids.ContainsKey("{$productCode}")

            # Try unpacking MSI compressed GUID -> standard {GUID} format
            if (-not $matchFound -and $productCode.Length -eq 32) {
                try {
                    $p  = $productCode
                    $sg = "{$($p[7])$($p[6])$($p[5])$($p[4])$($p[3])$($p[2])$($p[1])$($p[0])" +
                          "-$($p[11])$($p[10])$($p[9])$($p[8])" +
                          "-$($p[15])$($p[14])$($p[13])$($p[12])" +
                          "-$($p[17])$($p[16])$($p[19])$($p[18])" +
                          "-$($p[21])$($p[20])$($p[23])$($p[22])$($p[25])$($p[24])$($p[27])$($p[26])$($p[29])$($p[28])$($p[31])$($p[30])}"
                    if ($knownGuids.ContainsKey($sg)) { $matchFound = $true }
                } catch { }
            }

            # Check cached MSI package (only flag if local drive exists but file doesn't)
            $cachedMsi        = $msiProps.LocalPackage
            $hasMissingPackage = $false
            if (-not [string]::IsNullOrWhiteSpace($cachedMsi) -and $cachedMsi -match '^([A-Za-z]):\\') {
                if ((Test-Path "$($Matches[1]):\") -and -not (Test-Path $cachedMsi -EA 0)) {
                    $hasMissingPackage = $true
                }
            }

            if (-not $matchFound -or $hasMissingPackage) {
                $staleMsiEntries += [PSCustomObject]@{
                    Path=$msiKey.PSPath; ProductCode=$productCode
                    ProductName=if($msiProps.ProductName){$msiProps.ProductName}else{"(Unknown)"}
                    OrphanedEntry=(-not $matchFound); MissingCache=$hasMissingPackage; CachePath=$cachedMsi
                }
            }
        }
    }

    # --- Scan Patch Cache ---
    $patchCachePath  = "$env:SystemRoot\Installer"
    $orphanedPatches = 0
    $patchSizeBytes  = 0

    if (Test-Path $patchCachePath) {
        $referencedPatches = @{}
        $patchKeyPath = "HKLM:\SOFTWARE\Classes\Installer\Patches"
        if (Test-Path $patchKeyPath) {
            Get-ChildItem $patchKeyPath -EA 0 | ForEach-Object {
                $lp = (Get-ItemProperty $_.PSPath -EA 0).LocalPackage
                if ($lp) { $referencedPatches[$lp] = $true }
            }
        }
        Get-ChildItem $patchCachePath -Filter "*.msp" -EA 0 | ForEach-Object {
            if (-not $referencedPatches.ContainsKey($_.FullName)) {
                $orphanedPatches++
                $patchSizeBytes += $_.Length
            }
        }
    }

    # Return everything as a structured result
    return @{
        TotalScanned    = $totalScanned
        OrphanedHigh    = $orphanedHigh
        OrphanedMedium  = $orphanedMedium
        BrokenEntries   = $brokenEntries
        UnavailEntries  = $unavailEntries
        DuplicateEntries = $duplicateEntries
        StaleMsiEntries = $staleMsiEntries
        MsiScanned      = $msiScanned
        OrphanedPatches = $orphanedPatches
        PatchSizeMB     = [Math]::Round($patchSizeBytes / 1MB, 2)
        UninstallPaths  = $uninstallPaths
    }
}

# ---------------------------------------------------------------------
# CORE: Format scan results for display in the log window
# ---------------------------------------------------------------------
function Write-ScanReport {
    param([hashtable]$Scan)

    Write-Output ""
    Write-Output "[PHASE 1 RESULTS] Uninstall Registry"
    Write-Output "  Total entries scanned   : $($Scan.TotalScanned)"
    Write-Output "  Orphaned HIGH conf      : $($Scan.OrphanedHigh.Count)"
    Write-Output "  Orphaned MEDIUM conf    : $($Scan.OrphanedMedium.Count)"
    Write-Output "  Broken (bad path)       : $($Scan.BrokenEntries.Count)"
    Write-Output "  Unavailable (offline)   : $($Scan.UnavailEntries.Count) (SAFE - will NOT be touched)"
    Write-Output "  Duplicate names         : $($Scan.DuplicateEntries.Count)"
    Write-Output ""
    Write-Output "[PHASE 2 RESULTS] MSI Products"
    Write-Output "  MSI Products scanned    : $($Scan.MsiScanned)"
    Write-Output "  Stale MSI entries       : $($Scan.StaleMsiEntries.Count)"
    Write-Output ""
    Write-Output "[PHASE 3 RESULTS] Patch Cache"
    Write-Output "  Orphaned .msp patches   : $($Scan.OrphanedPatches) ($($Scan.PatchSizeMB) MB)"
    Write-Output ""

    # Detailed findings
    if ($Scan.OrphanedHigh.Count -gt 0) {
        Write-Output "--- ORPHANED ENTRIES (HIGH Confidence - safe to remove) ---"
        foreach ($e in $Scan.OrphanedHigh) { Write-Output "  [HIGH]   $($e.KeyName) - $($e.Reason)" }
        Write-Output ""
    }
    if ($Scan.OrphanedMedium.Count -gt 0) {
        Write-Output "--- ORPHANED ENTRIES (MEDIUM Confidence - will be SKIPPED) ---"
        foreach ($e in $Scan.OrphanedMedium) { Write-Output "  [MEDIUM] $($e.KeyName) - $($e.Reason)" }
        Write-Output ""
    }
    if ($Scan.BrokenEntries.Count -gt 0) {
        Write-Output "--- BROKEN UNINSTALL PATHS ---"
        foreach ($e in $Scan.BrokenEntries) {
            Write-Output "  [BROKEN] $($e.DisplayName)"
            Write-Output "           Key: $($e.KeyName) | $($e.Reason)"
        }
        Write-Output ""
    }
    if ($Scan.UnavailEntries.Count -gt 0) {
        Write-Output "--- UNAVAILABLE PATHS (Offline/Network - IGNORED) ---"
        foreach ($e in $Scan.UnavailEntries) { Write-Output "  [OFFLINE] $($e.DisplayName) - $($e.Reason)" }
        Write-Output ""
    }
    if ($Scan.StaleMsiEntries.Count -gt 0) {
        Write-Output "--- STALE MSI PRODUCT ENTRIES ---"
        foreach ($e in $Scan.StaleMsiEntries) {
            $flags = @(); if ($e.OrphanedEntry) { $flags += "ORPHANED" }; if ($e.MissingCache) { $flags += "MISSING-CACHE" }
            Write-Output "  [$($flags -join ', ')] $($e.ProductName)"
        }
        Write-Output ""
    }
    if ($Scan.DuplicateEntries.Count -gt 0) {
        Write-Output "--- DUPLICATE PROGRAM NAMES (Informational) ---"
        foreach ($d in $Scan.DuplicateEntries) { Write-Output "  [$($d.Count)x] $($d.DisplayName)" }
        Write-Output ""
    }
}

# ---------------------------------------------------------------------
# CORE: Backup a list of registry paths to .reg files
# Returns: array of backup target objects with .BackupFile property
# ---------------------------------------------------------------------
function Backup-RegistryKeys {
    param(
        [string]$BackupDir,
        [array]$OrphanedHigh,
        [array]$BrokenEntries,
        [array]$StaleMsiEntries
    )

    New-Item -Path $BackupDir -ItemType Directory -Force | Out-Null
    $targets    = @()
    $backupIdx  = 0

    foreach ($entry in $OrphanedHigh) {
        $backupIdx++
        $safeName   = ($entry.KeyName -replace '[\\/:*?"<>|]', '_')
        $backupFile = Join-Path $BackupDir "orphan_${backupIdx}_${safeName}.reg"
        $nativePath = $entry.Path -replace '^HKLM:\\','HKEY_LOCAL_MACHINE\' -replace '^HKCU:\\','HKEY_CURRENT_USER\'
        reg export $nativePath $backupFile /y 2>&1 | Out-Null
        $targets += [PSCustomObject]@{ Type="ORPHAN"; Path=$entry.Path; Label=$entry.KeyName; BackupFile=$backupFile }
    }

    foreach ($entry in $BrokenEntries) {
        $backupIdx++
        $safeName   = ($entry.KeyName -replace '[\\/:*?"<>|]', '_')
        $backupFile = Join-Path $BackupDir "broken_${backupIdx}_${safeName}.reg"
        $nativePath = $entry.Path -replace '^HKLM:\\','HKEY_LOCAL_MACHINE\' -replace '^HKCU:\\','HKEY_CURRENT_USER\'
        reg export $nativePath $backupFile /y 2>&1 | Out-Null
        $targets += [PSCustomObject]@{ Type="BROKEN"; Path=$entry.Path; Label="$($entry.DisplayName) ($($entry.KeyName))"; BackupFile=$backupFile }
    }

    foreach ($entry in ($StaleMsiEntries | Where-Object { $_.OrphanedEntry -eq $true })) {
        $backupIdx++
        $safeCode   = ($entry.ProductCode -replace '[\\/:*?"<>|]', '_')
        $backupFile = Join-Path $BackupDir "msi_${backupIdx}_${safeCode}.reg"
        $nativePath = $entry.Path -replace '^HKLM:\\','HKEY_LOCAL_MACHINE\' -replace '^HKCU:\\','HKEY_CURRENT_USER\'
        reg export $nativePath $backupFile /y 2>&1 | Out-Null
        $targets += [PSCustomObject]@{ Type="STALE_MSI"; Path=$entry.Path; Label=$entry.ProductName; BackupFile=$backupFile }
    }

    return $targets
}

# ---------------------------------------------------------------------
# CORE: Execute repairs on backed-up targets + re-register MSI engine
# Returns: hashtable with .Repaired and .Failed counts
# ---------------------------------------------------------------------
function Invoke-InstallRepair {
    param([array]$Targets)

    $repaired = 0
    $failed   = 0
    $log      = @()

    foreach ($target in $Targets) {
        try {
            Remove-Item $target.Path -Recurse -Force -EA Stop
            $log += "  [V] [$($target.Type)] $($target.Label)"
            $repaired++
        } catch {
            $log += "  [!] [$($target.Type)] FAILED: $($target.Label)"
            $log += "       $($_.Exception.Message)"
            $failed++
        }
    }

    # Re-register Windows Installer
    $log += ""
    $log += "  [FIX] Re-registering Windows Installer engine..."
    try {
        $null = msiexec /unregserver 2>&1
        Start-Sleep -Seconds 2
        $null = msiexec /regserver 2>&1
        Start-Sleep -Seconds 1
        $log += "  [V] Windows Installer re-registered."
        $repaired++
    } catch {
        $log += "  [!] Re-registration issue: $($_.Exception.Message)"
        $failed++
    }

    return @{ Repaired=$repaired; Failed=$failed; Log=$log }
}

# ---------------------------------------------------------------------
# CORE: Post-repair verification scan (lightweight)
# ---------------------------------------------------------------------
function Write-PostRepairVerification {
    param([array]$UninstallPaths)

    $postTotal = 0; $postOrphaned = 0
    foreach ($regPath in $UninstallPaths) {
        if (Test-Path $regPath) {
            Get-ChildItem $regPath -EA 0 | ForEach-Object {
                $postTotal++
                $p = Get-ItemProperty $_.PSPath -EA 0
                if ([string]::IsNullOrWhiteSpace($p.DisplayName)) { $postOrphaned++ }
            }
        }
    }
    Write-Output "  Remaining entries       : $postTotal"
    Write-Output "  Remaining orphans       : $postOrphaned"
}