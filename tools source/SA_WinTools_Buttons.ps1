# SA WinTools Professional v20.10 - Button Definitions
# Copyright (c) 2026 - Antoniou Stavros. AI-Assisted Development.
# Dot-sourced by SA_WinTools.ps1 — all parent variables are in scope.

# ============================================================
# BUTTON & POPUP FACTORY HELPERS
# ============================================================
function New-Btn {
    param(
        [string]$text, [int]$x,
        [Drawing.Color]$fg, [Drawing.Color]$bg,
        [Drawing.Color]$bdr, [Drawing.Color]$hov
    )
    $b = New-Object Windows.Forms.Button
    $b.Text      = $text
    $b.Location  = New-Object Drawing.Point($x, 26)
    $b.Size      = New-Object Drawing.Size(175, 52)
    $b.FlatStyle = 'Flat'
    $b.ForeColor = $fg
    $b.BackColor = $bg
    $b.Font      = $fB
    $b.FlatAppearance.BorderColor          = $bdr
    $b.FlatAppearance.BorderSize           = 1
    $b.FlatAppearance.MouseOverBackColor   = $hov
    return $b
}

function New-Popup {
    param([string]$title, [int]$w, [int]$h)
    $p = New-Object Windows.Forms.Form
    $p.Text            = $title
    $p.Size            = New-Object Drawing.Size($w, $h)
    $p.StartPosition   = 'CenterParent'
    $p.BackColor       = [Drawing.Color]::FromArgb(255, 12, 12, 12)
    $p.ForeColor       = [Drawing.Color]::White
    $p.FormBorderStyle = 'FixedDialog'
    $p.MaximizeBox     = $false
    return $p
}

function New-PopupLabel {
    param($popup, [string]$text, [int]$y)
    $l = New-Object Windows.Forms.Label
    $l.Text     = $text
    $l.Location = New-Object Drawing.Point(20, $y)
    $l.AutoSize = $true
    $l.Font     = $fS
    $popup.Controls.Add($l)
    return $l
}

function New-RadioPanel {
    param($popup, [int]$y, [int]$h)
    $p = New-Object Windows.Forms.Panel
    $p.Location  = New-Object Drawing.Point(20, $y)
    $p.Size      = New-Object Drawing.Size(370, $h)
    $p.BackColor = [Drawing.Color]::Transparent
    $popup.Controls.Add($p)
    return $p
}

function New-Radio {
    param($panel, [string]$text, [int]$y, [bool]$checked = $false)
    $rb = New-Object Windows.Forms.RadioButton
    $rb.Text     = $text
    $rb.Location = New-Object Drawing.Point(0, $y)
    $rb.AutoSize = $true
    $rb.Font     = $fS
    $rb.Checked  = $checked
    $panel.Controls.Add($rb)
    return $rb
}

function New-ExecBtn {
    param($popup, [int]$y, [int]$w = 370, [string]$text = 'EXECUTE')
    $ok = New-Object Windows.Forms.Button
    $ok.Text     = $text
    $ok.Location = New-Object Drawing.Point(20, $y)
    $ok.Size     = New-Object Drawing.Size($w, 48)
    $ok.FlatStyle = 'Flat'
    $ok.BackColor = [Drawing.Color]::FromArgb(255, 14, 14, 14)
    $ok.ForeColor = [Drawing.Color]::Cyan
    $ok.Font      = $fB
    $ok.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(255, 25, 75, 85)
    $ok.FlatAppearance.BorderSize  = 1
    $ok.FlatAppearance.MouseOverBackColor = [Drawing.Color]::FromArgb(255, 8, 40, 46)
    $ok.DialogResult = [Windows.Forms.DialogResult]::OK
    $popup.Controls.Add($ok)
    return $ok
}

# ============================================================
# ROW 1 — SYSTEM REPAIR
# x positions: 25, 215, 405, 595, 785
# ============================================================

# --- SFC Repair ---
$btn4 = New-Btn 'SFC Repair' 25 $clrR1 $clrR1btn $clrR1bdr $clrR1hov
$btn4.Add_Click({ &$cmdClick 'SFC Repair' 'sfc /scannow' })
$pR1.Controls.Add($btn4)

# --- DISM Clean ---
$btn2 = New-Btn 'DISM Clean' 215 $clrR1 $clrR1btn $clrR1bdr $clrR1hov
$btn2.Add_Click({ &$cmdClick 'DISM Clean' 'dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase' })
$pR1.Controls.Add($btn2)

# --- DISM Repair ---
$btn5 = New-Btn 'DISM Repair' 405 $clrR1 $clrR1btn $clrR1bdr $clrR1hov
$btn5.Add_Click({ &$cmdClick 'DISM Repair' 'dism.exe /Online /Cleanup-Image /RestoreHealth' })
$pR1.Controls.Add($btn5)

# --- Fix Win Update ---
$btn7 = New-Btn 'Fix Win Update' 595 $clrR1 $clrR1btn $clrR1bdr $clrR1hov
$btn7.Add_Click({ &$actionClick 'Fix Win Update' {
    $s = @('wuauserv', 'bits', 'cryptsvc', 'appidsvc')
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
}})
$pR1.Controls.Add($btn7)

# --- WinRE Manager ---
$btn10 = New-Btn 'WinRE Manager' 785 $clrR1 $clrR1btn $clrR1bdr $clrR1hov
$btn10.Add_Click({ &$actionClick 'WinRE Manager' {
    Write-Output '============================================================'
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
}})
$pR1.Controls.Add($btn10)

# ============================================================
# ROW 2 — MAINTENANCE
# ============================================================

# --- Cleanup ---
$btn1 = New-Btn 'Cleanup' 25 $clrR2 $clrR2btn $clrR2bdr $clrR2hov
$btn1.Add_Click({ &$actionClick 'Cleanup' {
    $cleanupTargets = @(
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
}})
$pR2.Controls.Add($btn1)

# --- Disk Analyzer ---
$btn17 = New-Btn 'Disk Analyzer' 215 $clrR2 $clrR2btn $clrR2bdr $clrR2hov
$btn17.Add_Click({
    $popup = New-Popup 'SA WinTools - Disk Space Analyzer' 420 262
    New-PopupLabel $popup 'Select Disk Analysis Operation:' 15
    $rg = New-RadioPanel $popup 45 108
    $rb1 = New-Radio $rg 'Drive Summary (size, used, free % for all drives)'  0  $true
    $rb2 = New-Radio $rg 'Large Files - Select Drive (files over 500 MB)'    37
    $rb3 = New-Radio $rg 'Top 10 Largest Folders - Select Drive'             74
    New-ExecBtn $popup 172 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Disk Analyzer - Drive Summary' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Drive Summary'
                Write-Output '============================================================'
                Write-Output ''
                Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null } |
                    Select-Object Name,
                        @{n='Total(GB)'; e={[math]::Round(($_.Used + $_.Free)/1GB, 1)}},
                        @{n='Used(GB)';  e={[math]::Round($_.Used/1GB, 1)}},
                        @{n='Free(GB)';  e={[math]::Round($_.Free/1GB, 1)}},
                        @{n='Free%';     e={[math]::Round($_.Free/($_.Used+$_.Free)*100, 1)}} |
                    Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] Drive summary completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked -or $rb3.Checked) {
            $allDrives = @(Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null })
            $dPopup = New-Popup 'Select Drive to Scan' 420 262
            New-PopupLabel $dPopup 'Select drive to scan:' 15

            $dList = New-Object Windows.Forms.ListBox
            $dList.Location  = New-Object Drawing.Point(20, 40)
            $dList.Size      = New-Object Drawing.Size(365, 128)
            $dList.BackColor = [Drawing.Color]::FromArgb(255, 6, 6, 6)
            $dList.ForeColor = [Drawing.Color]::FromArgb(255, 0, 224, 96)
            $dList.Font      = $fS
            foreach ($d in $allDrives) {
                $total = [math]::Round(($d.Used + $d.Free) / 1GB, 1)
                $free  = [math]::Round($d.Free / 1GB, 1)
                [void]$dList.Items.Add("$($d.Name):\  -  Total: ${total} GB   Free: ${free} GB")
            }
            if ($dList.Items.Count -gt 0) { $dList.SelectedIndex = 0 }
            $dPopup.Controls.Add($dList)
            New-ExecBtn $dPopup 182 365 'SCAN' > $null

            $rb2sel = $rb2.Checked
            if ($dPopup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK -and $dList.SelectedIndex -ne -1) {
                $selectedRoot = $allDrives[$dList.SelectedIndex].Root
                if ($rb2sel) {
                    &$actionClick "Disk Analyzer - Large Files ($selectedRoot)" {
                        $root = $using:selectedRoot
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
                            $found | Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                            Write-Output "[INFO] $($found.Count) file(s) over 500 MB found."
                        } else { Write-Output "[OK] No files over 500 MB found on $root" }
                        Write-Output '[SUCCESS] Large file scan completed.'
                        Write-Output '============================================================'
                    }
                } else {
                    &$actionClick "Disk Analyzer - Top Folders ($selectedRoot)" {
                        $root = $using:selectedRoot
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
                            Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                        Write-Output '[SUCCESS] Top folder analysis completed.'
                        Write-Output '============================================================'
                    }
                }
            }
        }
    }
})
$pR2.Controls.Add($btn17)

# --- Reset Spooler ---
$btn6 = New-Btn 'Reset Spooler' 405 $clrR2 $clrR2btn $clrR2bdr $clrR2hov
$btn6.Add_Click({ &$actionClick 'Reset Spooler' {
    Write-Output '[STEP 1] Stopping Spooler...'
    Stop-Service 'Spooler' -Force -EA 0
    Write-Output '[STEP 2] Clearing print queue...'
    Get-ChildItem "$env:SystemRoot\System32\spool\PRINTERS\*" -Recurse -EA 0 | Remove-Item -Force -Recurse -EA 0
    Write-Output '[STEP 3] Restarting Spooler...'
    Start-Service 'Spooler' -EA 0
    Write-Output '[SUCCESS] Spooler reset completed.'
}})
$pR2.Controls.Add($btn6)

# --- Install/Uninstall ---
$btn8 = New-Btn 'Install/Uninstall' 595 $clrR2 $clrR2btn $clrR2bdr $clrR2hov
$btn8.Add_Click({
    $popup = New-Popup 'SA WinTools - Install/Uninstall Manager' 420 238
    New-PopupLabel $popup 'Select Install/Uninstall Operation:' 15
    $rg = New-RadioPanel $popup 45 75
    $rb1 = New-Radio $rg 'Scan (Read-Only) - Diagnose registry issues'         0  $true
    $rb2 = New-Radio $rg 'Fix (Backup + Repair) - Remove orphaned entries'    37
    New-ExecBtn $popup 143 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            $localLibPath = $libPath
            &$actionClick 'Scan Install/Uninstall' {
                $lib = $using:localLibPath; . $lib
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
            }
        } elseif ($rb2.Checked) {
            $confirmResult = [System.Windows.Forms.MessageBox]::Show(
                "This will:`n`n  1. Create a timestamped registry backup (.reg files)`n  2. Remove orphaned ghost entries (HIGH confidence only)`n  3. Clean entries with verified broken uninstall paths`n  4. Remove orphaned MSI product entries`n  5. Re-register Windows Installer engine`n`nSAFETY FEATURES:`n  - Offline/network/removable drive entries are NEVER touched`n  - System components are excluded`n  - MEDIUM confidence orphans are skipped`n  - Full .reg backup enables one-click undo`n`nTip: Run Scan mode first to preview changes.`n`nBackup: $backupRoot\<timestamp>\`n`nProceed with repair?",
                'SA WinTools - Confirm Repair',
                [System.Windows.Forms.MessageBoxButtons]::YesNo,
                [System.Windows.Forms.MessageBoxIcon]::Warning)
            if ($confirmResult -ne [System.Windows.Forms.DialogResult]::Yes) {
                $t1.Text = 'CANCELLED: Fix Install/Uninstall'; return
            }
            $localLibPath    = $libPath
            $localBackupRoot = $backupRoot
            &$actionClick 'Fix Install/Uninstall' {
                $lib    = $using:localLibPath
                $bkRoot = $using:localBackupRoot
                . $lib
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
            }
        }
    }
})
$pR2.Controls.Add($btn8)

# --- Flush Network ---
$btn3 = New-Btn 'Flush Network' 785 $clrR2 $clrR2btn $clrR2bdr $clrR2hov
$btn3.Add_Click({
    $popup = New-Popup 'SA WinTools - Network Reset' 420 370
    New-PopupLabel $popup 'Select Network Reset Operation:' 15
    $rg = New-RadioPanel $popup 45 228
    $rb1 = New-Radio $rg 'Flush DNS (ipconfig /flushdns)'                      0  $true
    $rb2 = New-Radio $rg 'Winsock Reset (netsh winsock reset)'                38
    $rb3 = New-Radio $rg 'IP Reset (netsh int ip reset)'                      76
    $rb4 = New-Radio $rg 'Release IP (ipconfig /release)'                    114
    $rb5 = New-Radio $rg 'Renew IP (ipconfig /renew)'                        152
    $rb6 = New-Radio $rg 'Reset Network Credentials (drives + Kerberos)'     190
    New-ExecBtn $popup 288 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Flush DNS' {
                Write-Output '[*] Flushing DNS Resolver Cache...'
                ipconfig /flushdns *>&1 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] DNS cache flushed. No reboot required.'
            }
        } elseif ($rb2.Checked) {
            &$actionClick 'Winsock Reset' {
                Write-Output '[*] Resetting Winsock Catalog...'
                netsh winsock reset *>&1 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] Winsock reset completed.'
                Write-Output '[!] REBOOT REQUIRED for changes to take effect.'
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'IP Reset' {
                Write-Output '[*] Resetting all IP interface configurations...'
                netsh int ip reset *>&1 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] IP configuration reset completed.'
                Write-Output '[!] REBOOT REQUIRED for changes to take effect.'
            }
        } elseif ($rb4.Checked) {
            &$actionClick 'Release IP' {
                Write-Output '[*] Releasing current IP address...'
                ipconfig /release *>&1 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] IP address released. Network connectivity will drop momentarily.'
            }
        } elseif ($rb5.Checked) {
            &$actionClick 'Renew IP' {
                Write-Output '[*] Requesting new IP address from DHCP...'
                ipconfig /renew *>&1 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] IP address renewal requested.'
            }
        } elseif ($rb6.Checked) {
            $confirmResult = [System.Windows.Forms.MessageBox]::Show(
                "This will disconnect all mapped network drives and restart Explorer.`n`nThe desktop and taskbar will briefly disappear.`nUnsaved work in Explorer windows will be lost.`n`nContinue?",
                'SA WinTools - Confirm Network Credential Reset',
                [System.Windows.Forms.MessageBoxButtons]::YesNo,
                [System.Windows.Forms.MessageBoxIcon]::Warning)
            if ($confirmResult -eq [System.Windows.Forms.DialogResult]::Yes) {
                &$actionClick 'Reset Network Credentials' {
                    $ProgressPreference = 'SilentlyContinue'
                    Write-Output '============================================================'
                    Write-Output ' SA WinTools - Reset Network Credentials'
                    Write-Output '============================================================'
                    Write-Output ''
                    Write-Output '[STEP 1] Disconnecting all mapped network drives...'
                    net use * /delete /y *>&1 | Out-String -Width 500 | Write-Output
                    Write-Output ''
                    Write-Output '[STEP 2] Purging cached Kerberos authentication tickets...'
                    klist purge *>&1 | Out-String -Width 500 | Write-Output
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
                }
            }
        }
    }
})
$pR2.Controls.Add($btn3)

# ============================================================
# ROW 3 — HARDWARE & DIAGNOSTICS
# ============================================================

# --- Trim SSD ---
$btn11 = New-Btn 'Trim SSD' 25 $clrR3 $clrR3btn $clrR3bdr $clrR3hov
$btn11.Add_Click({
    try {
        $allPhysicalDisks = Get-PhysicalDisk -EA SilentlyContinue
        $ssds = $allPhysicalDisks | Where-Object { $_.MediaType -eq 'SSD' -or $_.FriendlyName -like '*SSD*' -or $_.BusType -eq 'NVMe' }
        if (-not $ssds) {
            $ssdDeviceNumbers = Get-Disk -EA SilentlyContinue | Where-Object { $_.IsSSD -or $_.MediaType -eq 'SSD' -or $_.Model -like '*SSD*' } | Select-Object -ExpandProperty Number -EA SilentlyContinue
        } else {
            $ssdDeviceNumbers = foreach ($s in $ssds) {
                if ($s.DeviceId) { [int]$s.DeviceId } elseif ($s.DeviceNumber) { [int]$s.DeviceNumber } elseif ($s.Number) { [int]$s.Number }
            }
        }
    } catch { $ssdDeviceNumbers = $null }

    if (-not $ssdDeviceNumbers) {
        [System.Windows.Forms.MessageBox]::Show('No SSD drives detected on this system.', 'SSD Trim', 0, 48); return
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
        [System.Windows.Forms.MessageBox]::Show('No accessible NTFS/ReFS volumes found on SSD drives.', 'SSD Trim', 0, 48); return
    }

    $popup = New-Popup 'Select SSD Volume to Trim' 420 295
    New-PopupLabel $popup 'Select volume to trim:' 15

    $list = New-Object Windows.Forms.ListBox
    $list.Location  = New-Object Drawing.Point(20, 40)
    $list.Size      = New-Object Drawing.Size(365, 148)
    $list.BackColor = [Drawing.Color]::FromArgb(255, 6, 6, 6)
    $list.ForeColor = [Drawing.Color]::FromArgb(255, 0, 224, 96)
    $list.Font      = $fS
    foreach ($v in $ssdVolumes) {
        [void]$list.Items.Add("$($v.DriveLetter): [$($v.FileSystemLabel)] - $([Math]::Round($v.Size/1GB,1)) GB")
    }
    if ($list.Items.Count -gt 0) { $list.SelectedIndex = 0 }
    $popup.Controls.Add($list)
    New-ExecBtn $popup 202 365 'TRIM' > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK -and $list.SelectedIndex -ne -1) {
        $selectedDrive = $ssdVolumes[$list.SelectedIndex].DriveLetter
        &$actionClick "Trim SSD ($($selectedDrive):)" {
            $drive = $using:selectedDrive
            $ProgressPreference = 'SilentlyContinue'
            Write-Output '============================================================'
            Write-Output " SA WinTools - SSD Trim  |  Target: $($drive):"
            Write-Output '============================================================'
            Write-Output ''
            Write-Output '[STEP 1] Starting Re-Trim operation...'
            Optimize-Volume -DriveLetter $drive -ReTrim -Verbose *>&1 | Out-String -Width 500 | Write-Output
            Write-Output ''
            Write-Output "[SUCCESS] Trim operation completed for $($drive):"
            Write-Output '============================================================'
        }
    }
})
$pR3.Controls.Add($btn11)

# --- Check HDD ---
$btn12 = New-Btn 'Check HDD' 215 $clrR3 $clrR3btn $clrR3bdr $clrR3hov
$btn12.Add_Click({
    try {
        $allPhysicalDisks = Get-PhysicalDisk -EA SilentlyContinue
        $hdds = $allPhysicalDisks | Where-Object { $_.MediaType -eq 'HDD' }
        if (-not $hdds) {
            $hddDeviceNumbers = Get-Disk -EA SilentlyContinue | Where-Object { $_.MediaType -eq 'HDD' } | Select-Object -ExpandProperty Number -EA SilentlyContinue
        } else {
            $hddDeviceNumbers = foreach ($h in $hdds) {
                if ($h.DeviceId) { [int]$h.DeviceId } elseif ($h.DeviceNumber) { [int]$h.DeviceNumber } elseif ($h.Number) { [int]$h.Number }
            }
        }
    } catch { $hddDeviceNumbers = $null }

    if (-not $hddDeviceNumbers) {
        [System.Windows.Forms.MessageBox]::Show('No mechanical (HDD) drives detected on this system.', 'Check HDD', 0, 48); return
    }

    $hddVolumes = New-Object System.Collections.Generic.List[PSObject]
    $partitions = Get-Partition -EA SilentlyContinue | Where-Object { $hddDeviceNumbers -contains [int]$_.DiskNumber }
    foreach ($p in $partitions) {
        try {
            $v = $p | Get-Volume -EA SilentlyContinue
            if ($v -and $v.DriveLetter -and $v.FileSystem -match 'NTFS|ReFS' -and -not ($hddVolumes | Where-Object { $_.DriveLetter -eq $v.DriveLetter })) {
                $hddVolumes.Add($v)
            }
        } catch {}
    }
    if ($hddVolumes.Count -eq 0) {
        [System.Windows.Forms.MessageBox]::Show('No accessible volumes found on HDD drives.', 'Check HDD', 0, 48); return
    }

    $popup = New-Popup 'SA WinTools - HDD Check Utility' 420 480
    New-PopupLabel $popup '1. Select HDD Volume:' 15

    $list = New-Object Windows.Forms.ListBox
    $list.Location  = New-Object Drawing.Point(20, 40)
    $list.Size      = New-Object Drawing.Size(365, 100)
    $list.BackColor = [Drawing.Color]::FromArgb(255, 6, 6, 6)
    $list.ForeColor = [Drawing.Color]::FromArgb(255, 0, 224, 96)
    $list.Font      = $fS
    foreach ($v in $hddVolumes) {
        [void]$list.Items.Add("$($v.DriveLetter): [$($v.FileSystemLabel)] - $([Math]::Round($v.Size/1GB,1)) GB")
    }
    $popup.Controls.Add($list)

    New-PopupLabel $popup '2. Select chkdsk Operation:' 155
    $modes = @(
        @{ Label = 'Simple Information (Read-Only)'; Cmd = '' }
        @{ Label = 'Auto Fix Errors (/f)';           Cmd = '/f' }
        @{ Label = 'Full Check & Bad Sectors (/r)';  Cmd = '/r' }
        @{ Label = 'Quick Online Analysis (/scan)';  Cmd = '/scan' }
    )
    $rg = New-RadioPanel $popup 178 160
    $radioButtons = New-Object System.Collections.Generic.List[Windows.Forms.RadioButton]
    for ($i = 0; $i -lt $modes.Count; $i++) {
        $rb = New-Radio $rg $modes[$i].Label ($i * 36) ($i -eq 0)
        $radioButtons.Add($rb)
    }
    New-ExecBtn $popup 356 365 'EXECUTE CHKDSK' > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK -and $list.SelectedIndex -ne -1) {
        $selectedDrive = $hddVolumes[$list.SelectedIndex].DriveLetter
        $selectedMode  = ''
        for ($i = 0; $i -lt $radioButtons.Count; $i++) {
            if ($radioButtons[$i].Checked) { $selectedMode = $modes[$i].Cmd; break }
        }
        &$actionClick "Check HDD ($($selectedDrive):)" {
            $drive = $using:selectedDrive; $mode = $using:selectedMode
            $modeText = if ($mode) { $mode } else { 'Read-Only' }
            Write-Output '============================================================'
            Write-Output " SA WinTools - HDD Check (chkdsk)"
            Write-Output " Target: $($drive):    Mode: $modeText"
            Write-Output '============================================================'
            Write-Output ''
            Write-Output '[*] Initializing chkdsk operation...'
            Write-Output '[!] If the drive is in use you may be asked to schedule on restart.'
            Write-Output ''
            Invoke-Expression "chkdsk $($drive): $mode *>&1" | Write-Output
            Write-Output ''
            Write-Output '[SUCCESS] Task completed.'
            Write-Output '============================================================'
        }
    }
})
$pR3.Controls.Add($btn12)

# --- Device Query ---
$btn13 = New-Btn 'Device Query' 405 $clrR3 $clrR3btn $clrR3bdr $clrR3hov
$btn13.Add_Click({
    $popup = New-Popup 'SA WinTools - Device Query' 420 486
    New-PopupLabel $popup 'Select Device Query Operation:' 15
    $rg = New-RadioPanel $popup 45 336
    $rb1 = New-Radio $rg 'Driver Query (Signed drivers - driverquery /si)'             0  $true
    $rb2 = New-Radio $rg 'HID Device Services (List ROOT\HIDCLASS devices)'           42
    $rb3 = New-Radio $rg 'Remove HID Errors (Remove errored ROOT\HIDCLASS devices)'   84
    $rb4 = New-Radio $rg 'Bluetooth Adapters (Info) - List all Bluetooth devices'    126
    $rb5 = New-Radio $rg 'Reset Bluetooth Adapter (Disable then re-enable)'          168
    $rb6 = New-Radio $rg 'Disk Drive Model & Status (wmic diskdrive get model,status)'  210
    $rb7 = New-Radio $rg 'Disk Drive Model & Size (wmic diskdrive get size,model)'     252
    $rb8 = New-Radio $rg 'Disk Drive Brief Info (wmic diskdrive list brief)'           294
    New-ExecBtn $popup 396 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Driver Query' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Signed Driver Query (driverquery /si)'
                Write-Output ' Sorting: Alphabetical by Device Name'
                Write-Output '============================================================'
                Write-Output ''
                Write-Output '[*] Querying system drivers...'
                Write-Output ''
                driverquery /si /fo csv | ConvertFrom-Csv | Sort-Object 'DeviceName' |
                    Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] Driver query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked) {
            &$actionClick 'HID Device Services' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - HID Device Services (ROOT\HIDCLASS)'
                Write-Output '============================================================'
                Write-Output ''
                Get-PnpDevice | Where-Object { $_.InstanceId -like 'ROOT\HIDCLASS*' } |
                    Select-Object FriendlyName, InstanceId,
                        @{n='Service'; e={(Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_Service').Data}} |
                    Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] HID device services query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'Remove HID Errors' {
                Write-Output '============================================================'
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
            }
        } elseif ($rb4.Checked) {
            &$actionClick 'Bluetooth Adapters - Info' {
                $ProgressPreference = 'SilentlyContinue'
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Bluetooth Adapters (Info)'
                Write-Output '============================================================'
                Write-Output ''
                $btDevices = Get-PnpDevice -Class Bluetooth -EA SilentlyContinue
                if ($btDevices) {
                    $btDevices | Select-Object FriendlyName, InstanceId, Status |
                        Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                    Write-Output "[INFO] Total Bluetooth devices found: $($btDevices.Count)"
                } else { Write-Output '[INFO] No Bluetooth devices found.' }
                Write-Output '[SUCCESS] Bluetooth device query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb5.Checked) {
            $confirmResult = [System.Windows.Forms.MessageBox]::Show(
                "This will disable then re-enable the Bluetooth adapter.`n`nBluetooth connections will drop briefly and reconnect.`n`nContinue?",
                'SA WinTools - Confirm Bluetooth Reset',
                [System.Windows.Forms.MessageBoxButtons]::YesNo,
                [System.Windows.Forms.MessageBoxIcon]::Warning)
            if ($confirmResult -eq [System.Windows.Forms.DialogResult]::Yes) {
                &$actionClick 'Reset Bluetooth Adapter' {
                    $ProgressPreference = 'SilentlyContinue'
                    Write-Output '============================================================'
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
                }
            }
        } elseif ($rb6.Checked) {
            &$actionClick 'Disk Drive Model & Status' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Disk Drive Model & Status'
                Write-Output ' Command: wmic diskdrive get model,status'
                Write-Output '============================================================'
                Write-Output ''
                cmd /c "wmic diskdrive get model,status" | Write-Output
                Write-Output '[SUCCESS] Disk drive model/status query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb7.Checked) {
            &$actionClick 'Disk Drive Model & Size' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Disk Drive Model & Size'
                Write-Output ' Command: wmic diskdrive get size,model'
                Write-Output '============================================================'
                Write-Output ''
                cmd /c "wmic diskdrive get size,model" | Write-Output
                Write-Output '[SUCCESS] Disk drive model/size query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb8.Checked) {
            &$actionClick 'Disk Drive Brief Info' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Disk Drive Brief Info'
                Write-Output ' Command: wmic diskdrive list brief'
                Write-Output '============================================================'
                Write-Output ''
                wmic diskdrive list brief | Write-Output
                Write-Output '[SUCCESS] Disk drive brief info query completed.'
                Write-Output '============================================================'
            }
        }
    }
})
$pR3.Controls.Add($btn13)

# --- Services Check ---
$btn16 = New-Btn 'Services Check' 595 $clrR3 $clrR3btn $clrR3bdr $clrR3hov
$btn16.Add_Click({
    $popup = New-Popup 'SA WinTools - Services Health Check' 440 278
    New-PopupLabel $popup 'Select Services Operation:' 15
    $rg = New-RadioPanel $popup 45 112
    $rg.Size = New-Object Drawing.Size(390, 112)
    $rb1 = New-Radio $rg 'Stopped Auto-Start Services (list only)'     0  $true
    $rb2 = New-Radio $rg 'Restart All Stopped Auto-Start Services'    37
    $rb3 = New-Radio $rg 'All Services - Full Status Report'          74
    $ok = New-ExecBtn $popup 178 390

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Services - Stopped Auto-Start' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Stopped Auto-Start Services'
                Write-Output '============================================================'
                Write-Output ''
                $stopped = Get-Service | Where-Object { $_.StartType -eq 'Automatic' -and $_.Status -ne 'Running' }
                if ($stopped) {
                    $stopped | Select-Object Name, DisplayName, Status, StartType |
                        Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                    Write-Output "[INFO] Total stopped auto-start services: $($stopped.Count)"
                } else { Write-Output '[OK] All Automatic services are running.' }
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked) {
            &$actionClick 'Services - Restart Stopped' {
                Write-Output '============================================================'
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
                        Select-Object Name, DisplayName, Status | Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                } else { Write-Output '[OK] All Automatic services are already running.' }
                Write-Output '[SUCCESS] Service restart pass completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'Services - Full Report' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Full Services Status Report'
                Write-Output '============================================================'
                Write-Output ''
                Get-Service | Sort-Object Status, DisplayName |
                    Select-Object Name, DisplayName, Status, StartType |
                    Format-Table -AutoSize | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] Services report completed.'
                Write-Output '============================================================'
            }
        }
    }
})
$pR3.Controls.Add($btn16)

# --- Event Errors ---
$btn18 = New-Btn 'Event Errors' 785 $clrR3 $clrR3btn $clrR3bdr $clrR3hov
$btn18.Add_Click({
    $popup = New-Popup 'SA WinTools - Event Log Viewer' 420 262
    New-PopupLabel $popup 'Select Event Log Query:' 15
    $rg = New-RadioPanel $popup 45 110
    $rb1 = New-Radio $rg 'System Errors - Last 24h (Critical + Error)'          0  $true
    $rb2 = New-Radio $rg 'Application Errors - Last 24h (Critical + Error)'    37
    $rb3 = New-Radio $rg 'BSOD / Kernel Crash History (Event ID 41, 1001)'     74
    New-ExecBtn $popup 172 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Event Errors - System' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - System Event Errors (Last 24 Hours)'
                Write-Output '============================================================'
                Write-Output ''
                $events = Get-WinEvent -FilterHashtable @{ LogName='System'; Level=1,2; StartTime=(Get-Date).AddHours(-24) } -EA SilentlyContinue | Select-Object -First 50
                if ($events) {
                    $events | Sort-Object TimeCreated -Descending |
                        Select-Object TimeCreated, Id, LevelDisplayName, ProviderName,
                            @{n='Message'; e={ $_.Message -replace '\r?\n',' ' | ForEach-Object { if ($_.Length -gt 120) { $_.Substring(0,120)+'...' } else { $_ } }}} |
                        Format-List | Out-String -Width 500 | Write-Output
                    Write-Output "[INFO] Events shown: $($events.Count) (max 50)"
                } else { Write-Output '[OK] No Critical/Error events in System log in the last 24h.' }
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked) {
            &$actionClick 'Event Errors - Application' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Application Event Errors (Last 24 Hours)'
                Write-Output '============================================================'
                Write-Output ''
                $events = Get-WinEvent -FilterHashtable @{ LogName='Application'; Level=1,2; StartTime=(Get-Date).AddHours(-24) } -EA SilentlyContinue | Select-Object -First 50
                if ($events) {
                    $events | Sort-Object TimeCreated -Descending |
                        Select-Object TimeCreated, Id, LevelDisplayName, ProviderName,
                            @{n='Message'; e={ $_.Message -replace '\r?\n',' ' | ForEach-Object { if ($_.Length -gt 120) { $_.Substring(0,120)+'...' } else { $_ } }}} |
                        Format-List | Out-String -Width 500 | Write-Output
                    Write-Output "[INFO] Events shown: $($events.Count) (max 50)"
                } else { Write-Output '[OK] No Critical/Error events in Application log in the last 24h.' }
                Write-Output '============================================================'
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'Event Errors - BSOD History' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - BSOD / Kernel Crash History'
                Write-Output '============================================================'
                Write-Output ''
                $crashes = Get-WinEvent -FilterHashtable @{ LogName='System'; Id=41,1001 } -EA SilentlyContinue | Select-Object -First 30
                if ($crashes) {
                    $crashes | Sort-Object TimeCreated -Descending |
                        Select-Object TimeCreated, Id, ProviderName,
                            @{n='Message'; e={ $_.Message -replace '\r?\n',' ' | ForEach-Object { if ($_.Length -gt 200) { $_.Substring(0,200)+'...' } else { $_ } }}} |
                        Format-List | Out-String -Width 500 | Write-Output
                    Write-Output "[INFO] Crash events found: $($crashes.Count)"
                } else { Write-Output '[OK] No BSOD or kernel crash events found in the System log.' }
                Write-Output '============================================================'
            }
        }
    }
})
$pR3.Controls.Add($btn18)

# ============================================================
# ROW 4 — SYSTEM INFO & STATUS
# ============================================================

# --- Time Sync ---
$btn14 = New-Btn 'Time Sync' 25 $clrR4 $clrR4btn $clrR4bdr $clrR4hov
$btn14.Add_Click({
    $popup = New-Popup 'SA WinTools - Time Sync Fix' 420 278
    New-PopupLabel $popup 'Select Time Sync Operation:' 15
    $rg = New-RadioPanel $popup 45 112
    $rb1 = New-Radio $rg 'Check Time Status (w32tm /query /status)'      0  $true
    $rb2 = New-Radio $rg 'Force Resync (w32tm /resync /force)'          37
    $rb3 = New-Radio $rg 'Re-register Time Service (full reset)'         74
    New-ExecBtn $popup 178 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Time Sync - Status' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Windows Time Service Status'
                Write-Output '============================================================'
                Write-Output ''
                w32tm /query /status *>&1 | Write-Output
                Write-Output ''
                w32tm /query /source *>&1 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] Time status query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked) {
            &$actionClick 'Time Sync - Force Resync' {
                Write-Output '============================================================'
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
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'Time Sync - Re-register' {
                Write-Output '============================================================'
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
            }
        }
    }
})
$pR4.Controls.Add($btn14)

# --- Activation ---
$btn15 = New-Btn 'Activation' 215 $clrR4 $clrR4btn $clrR4bdr $clrR4hov
$btn15.Add_Click({
    $popup = New-Popup 'SA WinTools - Windows Activation' 420 370
    New-PopupLabel $popup 'Select Activation Operation:' 15
    $rg = New-RadioPanel $popup 45 148
    $rg.Size = New-Object Drawing.Size(370, 148)
    $rb1 = New-Radio $rg 'Check Status (slmgr /xpr - expiry date)'         0  $true
    $rb2 = New-Radio $rg 'Full License Info (slmgr /dlv - detailed)'      37
    $rb3 = New-Radio $rg 'Activate Online (slmgr /ato)'                   74
    $rb4 = New-Radio $rg 'Enter New Product Key (slmgr /ipk)'            111

    $keyLabel = New-Object Windows.Forms.Label
    $keyLabel.Text     = 'Product Key (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX):'
    $keyLabel.Location = New-Object Drawing.Point(20, 205)
    $keyLabel.AutoSize = $true; $keyLabel.Font = $fS; $keyLabel.Visible = $false
    $popup.Controls.Add($keyLabel)

    $keyBox = New-Object Windows.Forms.TextBox
    $keyBox.Location  = New-Object Drawing.Point(20, 225)
    $keyBox.Size      = New-Object Drawing.Size(370, 26)
    $keyBox.Font      = New-Object Drawing.Font('Consolas', 11)
    $keyBox.BackColor = [Drawing.Color]::FromArgb(255, 22, 22, 22)
    $keyBox.ForeColor = [Drawing.Color]::White
    $keyBox.MaxLength = 29; $keyBox.Visible = $false
    $popup.Controls.Add($keyBox)

    $rb4.Add_CheckedChanged({
        $keyLabel.Visible = $rb4.Checked
        $keyBox.Visible   = $rb4.Checked
        if ($rb4.Checked) { $keyBox.Focus() }
    })

    New-ExecBtn $popup 270 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Activation - Status' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Windows Activation Status (slmgr /xpr)'
                Write-Output '============================================================'
                Write-Output ''
                cscript //nologo "$env:SystemRoot\System32\slmgr.vbs" /xpr *>&1 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] Activation status query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked) {
            &$actionClick 'Activation - Full Info' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Windows License Details (slmgr /dlv)'
                Write-Output '============================================================'
                Write-Output ''
                cscript //nologo "$env:SystemRoot\System32\slmgr.vbs" /dlv *>&1 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] License detail query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'Activation - Activate Online' {
                Write-Output '============================================================'
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
            }
        } elseif ($rb4.Checked) {
            $localKey = $keyBox.Text.Trim()
            if ($localKey -eq '') {
                [System.Windows.Forms.MessageBox]::Show(
                    'Please enter a product key before clicking Execute.',
                    'SA WinTools - Input Required', 0, 48)
            } else {
                &$actionClick 'Activation - Install Product Key' {
                    $key = $using:localKey
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
                }
            }
        }
    }
})
$pR4.Controls.Add($btn15)

# --- Network Info ---
$btn19 = New-Btn 'Network Info' 405 $clrR4 $clrR4btn $clrR4bdr $clrR4hov
$btn19.Add_Click({
    $popup = New-Popup 'SA WinTools - Network Info' 420 310
    New-PopupLabel $popup 'Select Network Info Query:' 15
    $rg = New-RadioPanel $popup 45 185
    $rb1 = New-Radio $rg 'Basic IP (ipconfig)'                                   0  $true
    $rb2 = New-Radio $rg 'Full Network Details (ipconfig /all)'                 37
    $rb3 = New-Radio $rg 'DNS Cache (ipconfig /displaydns)'                     74
    $rb4 = New-Radio $rg 'Active Connections (netstat)'                        111
    $rb5 = New-Radio $rg 'MAC Addresses (getmac /v)'                           148
    New-ExecBtn $popup 245 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Network Info - Basic IP' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Basic IP Information (ipconfig)'
                Write-Output '============================================================'
                Write-Output ''
                ipconfig *>&1 | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] Basic IP query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked) {
            &$actionClick 'Network Info - Full Details' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Full Network Details (ipconfig /all)'
                Write-Output '============================================================'
                Write-Output ''
                ipconfig /all *>&1 | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] Full network details query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'Network Info - DNS Cache' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - DNS Cache (ipconfig /displaydns)'
                Write-Output '============================================================'
                Write-Output ''
                ipconfig /displaydns *>&1 | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] DNS cache query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb4.Checked) {
            &$actionClick 'Network Info - Active Connections' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Active Network Connections (netstat)'
                Write-Output '============================================================'
                Write-Output ''
                netstat *>&1 | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] Active connections query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb5.Checked) {
            &$actionClick 'Network Info - MAC Addresses' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - MAC Addresses (getmac /v)'
                Write-Output '============================================================'
                Write-Output ''
                getmac /v *>&1 | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] MAC address query completed.'
                Write-Output '============================================================'
            }
        }
    }
})
$pR4.Controls.Add($btn19)

# --- Wi-Fi & Firewall ---
$btn20 = New-Btn 'Wi-Fi & Firewall' 595 $clrR4 $clrR4btn $clrR4bdr $clrR4hov
$btn20.Add_Click({
    $popup = New-Popup 'SA WinTools - Wi-Fi & Firewall' 420 430
    New-PopupLabel $popup 'Select Wi-Fi or Firewall Operation:' 15
    $rg = New-RadioPanel $popup 45 228
    $rg.Size = New-Object Drawing.Size(370, 228)
    $rb1 = New-Radio $rg 'Wi-Fi Profiles (netsh wlan show profiles)'              0  $true
    $rb2 = New-Radio $rg 'Wi-Fi Password (show saved key for a profile)'         38
    $rb3 = New-Radio $rg 'Wi-Fi Report (netsh wlan show wlanreport)'             76
    $rb4 = New-Radio $rg 'Firewall Status (show all profiles)'                  114
    $rb5 = New-Radio $rg 'Disable Firewall (set allprofiles state off)'         152
    $rb6 = New-Radio $rg 'Enable Firewall (set allprofiles state on)'           190

    $wifiNameLabel = New-Object Windows.Forms.Label
    $wifiNameLabel.Text     = 'Wi-Fi Profile Name (exact, case-sensitive):'
    $wifiNameLabel.Location = New-Object Drawing.Point(20, 283)
    $wifiNameLabel.AutoSize = $true; $wifiNameLabel.Font = $fS; $wifiNameLabel.Visible = $false
    $popup.Controls.Add($wifiNameLabel)

    $wifiNameBox = New-Object Windows.Forms.TextBox
    $wifiNameBox.Location  = New-Object Drawing.Point(20, 303)
    $wifiNameBox.Size      = New-Object Drawing.Size(370, 26)
    $wifiNameBox.Font      = New-Object Drawing.Font('Consolas', 11)
    $wifiNameBox.BackColor = [Drawing.Color]::FromArgb(255, 22, 22, 22)
    $wifiNameBox.ForeColor = [Drawing.Color]::White
    $wifiNameBox.MaxLength = 100; $wifiNameBox.Visible = $false
    $popup.Controls.Add($wifiNameBox)

    $rb2.Add_CheckedChanged({
        $wifiNameLabel.Visible = $rb2.Checked
        $wifiNameBox.Visible   = $rb2.Checked
        if ($rb2.Checked) { $wifiNameBox.Focus() }
    })

    New-ExecBtn $popup 345 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Wi-Fi Profiles' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Wi-Fi Saved Profiles'
                Write-Output '============================================================'
                Write-Output ''
                netsh wlan show profiles *>&1 | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] Wi-Fi profiles query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked) {
            $localWifiName = $wifiNameBox.Text.Trim()
            if ($localWifiName -eq '') {
                [System.Windows.Forms.MessageBox]::Show(
                    'Please enter a Wi-Fi profile name before clicking Execute.',
                    'SA WinTools - Input Required', 0, 48)
            } else {
                &$actionClick 'Wi-Fi Password' {
                    $profileName = $using:localWifiName
                    Write-Output '============================================================'
                    Write-Output " SA WinTools - Wi-Fi Password for: $profileName"
                    Write-Output '============================================================'
                    Write-Output ''
                    netsh wlan show profile name="$profileName" key=clear *>&1 | Out-String -Width 500 | Write-Output
                    Write-Output '[SUCCESS] Wi-Fi password query completed.'
                    Write-Output '============================================================'
                }
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'Wi-Fi Report' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Wi-Fi Connectivity Report'
                Write-Output '============================================================'
                Write-Output ''
                Write-Output '[*] Generating WLAN report (this may take a moment)...'
                netsh wlan show wlanreport *>&1 | Out-String -Width 500 | Write-Output
                Write-Output ''
                Write-Output '[INFO] Report saved to: C:\ProgramData\Microsoft\Windows\WlanReport\'
                Write-Output '[SUCCESS] Wi-Fi report generated.'
                Write-Output '============================================================'
            }
        } elseif ($rb4.Checked) {
            &$actionClick 'Firewall Status' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Windows Firewall Status (all profiles)'
                Write-Output '============================================================'
                Write-Output ''
                netsh advfirewall show allprofiles *>&1 | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] Firewall status query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb5.Checked) {
            $confirmResult = [System.Windows.Forms.MessageBox]::Show(
                "WARNING: This will disable Windows Firewall on ALL profiles.`n`nFor temporary diagnostic use ONLY.`nRe-enable immediately after testing.`n`nDisable firewall now?",
                'SA WinTools - Confirm Disable Firewall',
                [System.Windows.Forms.MessageBoxButtons]::YesNo,
                [System.Windows.Forms.MessageBoxIcon]::Warning)
            if ($confirmResult -eq [System.Windows.Forms.DialogResult]::Yes) {
                &$actionClick 'Firewall - Disable All' {
                    Write-Output '============================================================'
                    Write-Output ' SA WinTools - Disable Windows Firewall (All Profiles)'
                    Write-Output '============================================================'
                    Write-Output ''
                    netsh advfirewall set allprofiles state off *>&1 | Out-String -Width 500 | Write-Output
                    Write-Output ''
                    Write-Output '[WARNING] Firewall is now DISABLED on all profiles.'
                    Write-Output '[!] Re-enable immediately using Enable Firewall mode.'
                    Write-Output '============================================================'
                }
            }
        } elseif ($rb6.Checked) {
            &$actionClick 'Firewall - Enable All' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Enable Windows Firewall (All Profiles)'
                Write-Output '============================================================'
                Write-Output ''
                netsh advfirewall set allprofiles state on *>&1 | Out-String -Width 500 | Write-Output
                Write-Output ''
                Write-Output '[SUCCESS] Firewall re-enabled on all profiles.'
                Write-Output '============================================================'
            }
        }
    }
})
$pR4.Controls.Add($btn20)

# --- Power & System ---
$btn21 = New-Btn 'Power & System' 785 $clrR4 $clrR4btn $clrR4bdr $clrR4hov
$btn21.Add_Click({
    $popup = New-Popup 'SA WinTools - Power & System Info' 420 262
    New-PopupLabel $popup 'Select Power or System Operation:' 15
    $rg = New-RadioPanel $popup 45 114
    $rb1 = New-Radio $rg 'System Info (systeminfo - full hardware report)'      0  $true
    $rb2 = New-Radio $rg 'Energy Report (powercfg /energy - ~60 seconds)'      38
    $rb3 = New-Radio $rg 'Battery Report (powercfg /batteryreport)'            76
    New-ExecBtn $popup 172 > $null

    if ($popup.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ($rb1.Checked) {
            &$actionClick 'Power & System - System Info' {
                Write-Output '============================================================'
                Write-Output ' SA WinTools - System Information (systeminfo)'
                Write-Output '============================================================'
                Write-Output ''
                systeminfo *>&1 | Out-String -Width 500 | Write-Output
                Write-Output '[SUCCESS] System info query completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb2.Checked) {
            &$actionClick 'Power & System - Energy Report' {
                $ProgressPreference = 'SilentlyContinue'
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Energy Efficiency Report (powercfg /energy)'
                Write-Output '============================================================'
                Write-Output ''
                Write-Output '[*] Generating energy report - this takes approximately 60 seconds...'
                powercfg /energy *>&1 | Out-String -Width 500 | Write-Output
                $reportPath = "$env:SystemRoot\system32\energy-report.html"
                Write-Output ''
                if (Test-Path $reportPath) {
                    Write-Output "[INFO] Report saved to: $reportPath"
                    Write-Output '[*] Opening report in default browser...'
                    Start-Process $reportPath
                }
                Write-Output '[SUCCESS] Energy report completed.'
                Write-Output '============================================================'
            }
        } elseif ($rb3.Checked) {
            &$actionClick 'Power & System - Battery Report' {
                $ProgressPreference = 'SilentlyContinue'
                Write-Output '============================================================'
                Write-Output ' SA WinTools - Battery Health Report (powercfg /batteryreport)'
                Write-Output '============================================================'
                Write-Output ''
                Write-Output '[*] Generating battery report...'
                powercfg /batteryreport *>&1 | Out-String -Width 500 | Write-Output
                $reportPath = "$env:SystemRoot\system32\battery-report.html"
                Write-Output ''
                if (Test-Path $reportPath) {
                    Write-Output "[INFO] Report saved to: $reportPath"
                    Write-Output '[*] Opening report in default browser...'
                    Start-Process $reportPath
                }
                Write-Output '[SUCCESS] Battery report completed.'
                Write-Output '============================================================'
            }
        }
    }
})
$pR4.Controls.Add($btn21)
