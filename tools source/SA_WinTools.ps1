# SA WinTools Professional v20.10
# Copyright (c) 2026 - Antoniou Stavros. AI-Assisted Development.
# Requires: SA_WinTools_Lib.ps1 and SA_WinTools_Buttons.ps1 in same directory
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

# ============================================================
# PATH RESOLUTION
# ============================================================
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$libPath     = Join-Path $scriptDir 'SA_WinTools_Lib.ps1'
$btnPath     = Join-Path $scriptDir 'SA_WinTools_Buttons.ps1'
$backupRoot  = Join-Path $scriptDir 'SA_WinTools_RegBackup'

foreach ($req in @($libPath, $btnPath)) {
    if (-not (Test-Path $req)) {
        [System.Windows.Forms.MessageBox]::Show(
            "Missing required file:`n$req`n`nPlace all SA_WinTools files in the same folder.",
            'SA WinTools - Missing File', 0, 16)
        exit
    }
}

# ============================================================
# COLOR PALETTE
# ============================================================
$clrBg       = [Drawing.Color]::FromArgb(255,  0,  0,  0)   # Pure AMOLED black
$clrHeader   = [Drawing.Color]::FromArgb(255,  8,  8,  8)   # Header panel
$clrSep      = [Drawing.Color]::FromArgb(255, 28, 28, 28)   # Separator lines
$clrStatusBg = [Drawing.Color]::FromArgb(255,  8,  8,  8)   # Status panel bg

# Row panel tinted backgrounds
$clrR1bg  = [Drawing.Color]::FromArgb(255, 14,  7,  7)   # System Repair  - dark red tint
$clrR2bg  = [Drawing.Color]::FromArgb(255, 14, 12,  4)   # Maintenance    - dark gold tint
$clrR3bg  = [Drawing.Color]::FromArgb(255,  4,  8, 16)   # Diagnostics    - dark blue tint
$clrR4bg  = [Drawing.Color]::FromArgb(255,  4, 14,  8)   # Info/Status    - dark green tint

# Row accent colors (button foreground + border)
$clrR1    = [Drawing.Color]::FromArgb(255, 220,  70,  70)   # Muted red
$clrR2    = [Drawing.Color]::FromArgb(255, 210, 160,  40)   # Dark gold
$clrR3    = [Drawing.Color]::FromArgb(255,  50, 160, 220)   # Steel blue
$clrR4    = [Drawing.Color]::FromArgb(255,  50, 205, 130)   # Muted green

# Row button backgrounds (per button)
$clrR1btn = [Drawing.Color]::FromArgb(255, 22, 10, 10)
$clrR2btn = [Drawing.Color]::FromArgb(255, 20, 16,  5)
$clrR3btn = [Drawing.Color]::FromArgb(255,  6, 11, 22)
$clrR4btn = [Drawing.Color]::FromArgb(255,  6, 20, 11)

# Row button border colors (dimmed accent)
$clrR1bdr = [Drawing.Color]::FromArgb(255,  85, 28, 28)
$clrR2bdr = [Drawing.Color]::FromArgb(255,  85, 60, 16)
$clrR3bdr = [Drawing.Color]::FromArgb(255,  18, 55, 88)
$clrR4bdr = [Drawing.Color]::FromArgb(255,  16, 70, 40)

# Row button hover colors
$clrR1hov = [Drawing.Color]::FromArgb(255, 35, 14, 14)
$clrR2hov = [Drawing.Color]::FromArgb(255, 32, 24,  8)
$clrR3hov = [Drawing.Color]::FromArgb(255,  9, 16, 34)
$clrR4hov = [Drawing.Color]::FromArgb(255,  9, 30, 16)

# ============================================================
# FONTS
# ============================================================
$bold = [Drawing.FontStyle]::Bold
$fT   = New-Object Drawing.Font('Segoe UI', 20, $bold)     # Title
$fSub = New-Object Drawing.Font('Segoe UI',  8)             # Subtitle
$fCpy = New-Object Drawing.Font('Segoe UI',  8, $bold)     # Copyright
$fB   = New-Object Drawing.Font('Segoe UI',  9, $bold)     # Buttons
$fL   = New-Object Drawing.Font('Segoe UI', 11)             # Status text
$fS   = New-Object Drawing.Font('Segoe UI',  9, $bold)     # Small bold (popups)
$fCat = New-Object Drawing.Font('Segoe UI',  7, $bold)     # Category micro-labels
$fLog = New-Object Drawing.Font('Consolas', 10)             # Log monospace

# ============================================================
# HELPERS
# ============================================================
function New-SepLine {
    param([Windows.Forms.Control]$parent, [int]$y, [string]$anchor = 'Top, Left, Right')
    $ln = New-Object Windows.Forms.Panel
    $ln.Location  = New-Object Drawing.Point(0, $y)
    $ln.Size      = New-Object Drawing.Size(2000, 1)
    $ln.BackColor = $clrSep
    $ln.Anchor    = $anchor
    $parent.Controls.Add($ln)
    return $ln
}

function New-RowPanel {
    param([int]$y, [Drawing.Color]$bg, [Drawing.Color]$accent, [string]$catText)
    $p = New-Object Windows.Forms.Panel
    $p.Location  = New-Object Drawing.Point(0, $y)
    $p.Size      = New-Object Drawing.Size(2000, 84)
    $p.BackColor = $bg
    $p.Anchor    = 'Top, Left, Right'
    # Category micro-label at top-left of panel
    $lbl = New-Object Windows.Forms.Label
    $lbl.Text      = $catText
    $lbl.ForeColor = [Drawing.Color]::FromArgb(255, [int]($accent.R * 0.55), [int]($accent.G * 0.55), [int]($accent.B * 0.55))
    $lbl.Font      = $fCat
    $lbl.Location  = New-Object Drawing.Point(25, 5)
    $lbl.AutoSize  = $true
    $p.Controls.Add($lbl)
    return $p
}

# ============================================================
# MAIN FORM
# ============================================================
$f = New-Object Windows.Forms.Form
$f.Text            = 'SA WinTools Professional v20.10'
$f.Size            = New-Object Drawing.Size(1000, 995)
$f.MinimumSize     = New-Object Drawing.Size(900, 875)
$f.BackColor       = $clrBg
$f.StartPosition   = 'CenterScreen'
$f.FormBorderStyle = 'Sizable'
$f.MaximizeBox     = $true

# ============================================================
# HEADER PANEL  (h=85 — title + subtitle + copyright)
# ============================================================
$pHeader = New-Object Windows.Forms.Panel
$pHeader.Location  = New-Object Drawing.Point(0, 0)
$pHeader.Size      = New-Object Drawing.Size(2000, 100)
$pHeader.BackColor = $clrHeader
$pHeader.Anchor    = 'Top, Left, Right'
$f.Controls.Add($pHeader)

$lblTitle = New-Object Windows.Forms.Label
$lblTitle.Text      = 'SA WinTools Professional'
$lblTitle.ForeColor = [Drawing.Color]::FromArgb(255, 0, 220, 240)
$lblTitle.Font      = $fT
$lblTitle.Location  = New-Object Drawing.Point(20, 8)
$lblTitle.AutoSize  = $true
$pHeader.Controls.Add($lblTitle)

$lblSub = New-Object Windows.Forms.Label
$lblSub.Text      = 'Windows Maintenance Suite  -  v20.10'
$lblSub.ForeColor = [Drawing.Color]::FromArgb(255, 140, 140, 140)
$lblSub.Font      = $fSub
$lblSub.Location  = New-Object Drawing.Point(22, 52)
$lblSub.AutoSize  = $true
$pHeader.Controls.Add($lblSub)

$lblHeaderCopy = New-Object Windows.Forms.Label
$lblHeaderCopy.Text      = [char]0x00A9 + ' 2026 Antoniou Stavros. AI-Assisted Development.'
$lblHeaderCopy.ForeColor = [Drawing.Color]::FromArgb(255, 130, 130, 130)
$lblHeaderCopy.Font      = $fCpy
$lblHeaderCopy.Location  = New-Object Drawing.Point(22, 70)
$lblHeaderCopy.AutoSize  = $true
$pHeader.Controls.Add($lblHeaderCopy)

New-SepLine $f 100 | Out-Null

# ============================================================
# ROW GROUP PANELS  (h=84 each, 2px gap between rows)
# ============================================================
$pR1 = New-RowPanel -y 102 -bg $clrR1bg -accent $clrR1 -catText 'SYSTEM REPAIR'
$pR2 = New-RowPanel -y 188 -bg $clrR2bg -accent $clrR2 -catText 'MAINTENANCE'
$pR3 = New-RowPanel -y 274 -bg $clrR3bg -accent $clrR3 -catText 'HARDWARE & DIAGNOSTICS'
$pR4 = New-RowPanel -y 360 -bg $clrR4bg -accent $clrR4 -catText 'SYSTEM INFO & STATUS'

$f.Controls.Add($pR1)
$f.Controls.Add($pR2)
$f.Controls.Add($pR3)
$f.Controls.Add($pR4)

New-SepLine $f 446 | Out-Null

# ============================================================
# STATUS AREA  (y=447, h=110)
# ============================================================
$pStatus = New-Object Windows.Forms.Panel
$pStatus.Location  = New-Object Drawing.Point(0, 447)
$pStatus.Size      = New-Object Drawing.Size(2000, 110)
$pStatus.BackColor = $clrStatusBg
$pStatus.Anchor    = 'Top, Left, Right'
$f.Controls.Add($pStatus)

$lblStatus = New-Object Windows.Forms.Label
$lblStatus.Text      = 'CURRENT STATUS / TASK:'
$lblStatus.ForeColor = [Drawing.Color]::FromArgb(255, 70, 70, 70)
$lblStatus.Font      = $fCat
$lblStatus.Location  = New-Object Drawing.Point(25, 2)
$lblStatus.AutoSize  = $true
$pStatus.Controls.Add($lblStatus)

$t1 = New-Object Windows.Forms.TextBox
$t1.Multiline    = $true
$t1.Location     = New-Object Drawing.Point(25, 22)
$t1.Size         = New-Object Drawing.Size(950, 80)
$t1.BackColor    = [Drawing.Color]::FromArgb(255, 14, 14, 14)
$t1.ForeColor    = [Drawing.Color]::FromArgb(255, 0, 220, 240)
$t1.ReadOnly     = $true
$t1.Font         = $fL
$t1.BorderStyle  = 'FixedSingle'
$t1.Anchor       = 'Top, Left, Right'
$pStatus.Controls.Add($t1)

New-SepLine $f 557 | Out-Null

# ============================================================
# LOG AREA  (y=557)
# ============================================================
$lblLog = New-Object Windows.Forms.Label
$lblLog.Text      = 'DETAILED EXECUTION LOG:'
$lblLog.ForeColor = [Drawing.Color]::FromArgb(255, 70, 70, 70)
$lblLog.Font      = $fCat
$lblLog.Location  = New-Object Drawing.Point(25, 560)
$lblLog.AutoSize  = $true
$f.Controls.Add($lblLog)

$t2 = New-Object Windows.Forms.TextBox
$t2.Multiline   = $true
$t2.Location    = New-Object Drawing.Point(25, 580)
$t2.Size        = New-Object Drawing.Size(950, 295)
$t2.BackColor   = [Drawing.Color]::FromArgb(255, 0, 0, 0)
$t2.ForeColor   = [Drawing.Color]::FromArgb(255, 0, 224, 96)
$t2.ScrollBars  = 'Both'
$t2.WordWrap    = $false
$t2.ReadOnly    = $true
$t2.MaxLength   = 0
$t2.Font        = $fLog
$t2.BorderStyle = 'FixedSingle'
$t2.Anchor      = 'Top, Left, Right, Bottom'
$f.Controls.Add($t2)

$sepBottom = New-SepLine $f 881 'Bottom, Left, Right'

# ============================================================
# BOTTOM CONTROLS — centered, anchored to bottom
# ============================================================
$btnW    = 220
$btnH    = 60
$btnGap  = 10
$bottomY = 887

function New-BottomBtn {
    param([string]$text, [int]$x, [Drawing.Color]$fg, [Drawing.Color]$bg, [Drawing.Color]$bdr)
    $b = New-Object Windows.Forms.Button
    $b.Text      = $text
    $b.Location  = New-Object Drawing.Point($x, $bottomY)
    $b.Size      = New-Object Drawing.Size($btnW, $btnH)
    $b.FlatStyle = 'Flat'
    $b.ForeColor = $fg
    $b.BackColor = $bg
    $b.Font      = $fB
    $b.Anchor    = 'Bottom, Left'
    $b.FlatAppearance.BorderColor = $bdr
    $b.FlatAppearance.BorderSize  = 1
    return $b
}

# Calculate centered starting X for initial 1000px form width
$totalBtnW = 4 * $btnW + 3 * $btnGap   # 910px
$initStartX = [int](($f.ClientSize.Width - $totalBtnW) / 2)

$bLog = New-BottomBtn 'OPEN CURRENT LOG' $initStartX `
    ([Drawing.Color]::Cyan) `
    ([Drawing.Color]::FromArgb(255, 8, 24, 26)) `
    ([Drawing.Color]::FromArgb(255, 28, 80, 86))

$bClear = New-BottomBtn 'CLEAR' ($initStartX + $btnW + $btnGap) `
    ([Drawing.Color]::Yellow) `
    ([Drawing.Color]::FromArgb(255, 20, 18, 4)) `
    ([Drawing.Color]::FromArgb(255, 70, 64, 14))

$bStop = New-BottomBtn 'STOP ALL' ($initStartX + 2 * ($btnW + $btnGap)) `
    ([Drawing.Color]::Red) `
    ([Drawing.Color]::FromArgb(255, 22, 4, 4)) `
    ([Drawing.Color]::FromArgb(255, 80, 14, 14))

$bReboot = New-BottomBtn 'REBOOT' ($initStartX + 3 * ($btnW + $btnGap)) `
    ([Drawing.Color]::OrangeRed) `
    ([Drawing.Color]::FromArgb(255, 22, 8, 2)) `
    ([Drawing.Color]::FromArgb(255, 80, 28, 8))

$logPath = "$env:TEMP\SA_WinTools_Active.log"

$bLog.Add_Click({
    if (Test-Path $logPath) { Start-Process notepad.exe -ArgumentList $logPath }
})
$bClear.Add_Click({
    $State.Active = $false
    Get-Job | Remove-Job -Force -EA 0
    if (Test-Path $logPath) { Clear-Content $logPath }
    $t1.Text = 'READY'
    $t2.Clear()
})
$bStop.Add_Click({
    $t1.Text = 'TERMINATED'
    $State.Active = $false
    if ($State.Job) { Stop-Job -Job $State.Job -PassThru | Remove-Job -Force -EA 0 }
    Get-Process -Name 'sfc', 'dism', 'ipconfig' -EA 0 | Stop-Process -Force
})
$bReboot.Add_Click({
    $r = [System.Windows.Forms.MessageBox]::Show(
        "This will immediately restart your computer.`n`nAll unsaved work will be lost.`n`nProceed with reboot?",
        'SA WinTools - Confirm Reboot',
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning)
    if ($r -eq [System.Windows.Forms.DialogResult]::Yes) { shutdown /r /f /t 0 }
})

$f.Controls.AddRange(@($bLog, $bClear, $bStop, $bReboot))

# Re-center bottom buttons on resize
$f.Add_Resize({
    $cw = $f.ClientSize.Width
    if ($cw -lt 1) { return }
    $sx = [int](($cw - $totalBtnW) / 2)
    $bLog.Left    = $sx
    $bClear.Left  = $sx + $btnW + $btnGap
    $bStop.Left   = $sx + 2 * ($btnW + $btnGap)
    $bReboot.Left = $sx + 3 * ($btnW + $btnGap)
    # Also stretch t1 and t2 to match new width
    $iw = $cw - 50
    if ($iw -gt 100) {
        $t1.Width = $iw
        $t2.Width = $iw
    }
})

# ============================================================
# SHARED STATE & TIMER
# ============================================================
$State = [hashtable]::Synchronized(@{ Job = $null; Active = $false })

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 400
$timer.Add_Tick({
    if ($State.Active -and $State.Job -ne $null) {
        $data = Receive-Job -Job $State.Job -Keep
        if ($data) {
            $fullOutput = ($data | Out-String -Width 500).Trim()
            if ($fullOutput -and $fullOutput -ne $t2.Text) {
                $t2.Text = $fullOutput
                $t2.SelectionStart = $t2.TextLength
                $t2.ScrollToCaret()
                $fullOutput | Out-File -FilePath $logPath -Encoding utf8 -Force
            }
        }
        if ($State.Job.State -ne 'Running') {
            if ($t1.Text -ne 'TERMINATED') { $t1.Text = 'COMPLETED' }
            $State.Active = $false
        }
    }
})
$timer.Start()

# ============================================================
# ACTION HANDLERS
# ============================================================
$actionClick = {
    param($label, $script)
    if (Test-Path $logPath) { Clear-Content $logPath }
    Get-Job | Remove-Job -Force -EA 0
    $t2.Clear(); $t1.Text = "RUNNING: $label"
    $State.Job    = Start-Job -ScriptBlock $script
    $State.Active = $true
}

$cmdClick = {
    param($label, $command)
    if (Test-Path $logPath) { Clear-Content $logPath }
    Get-Job | Remove-Job -Force -EA 0
    $t2.Clear(); $t1.Text = "RUNNING: $label"
    $sb           = [scriptblock]::Create("$command *>&1")
    $State.Job    = Start-Job -ScriptBlock $sb
    $State.Active = $true
}

# ============================================================
# HELP BUTTON  (circular, header top-right, anchored)
# ============================================================
$btnHelp = New-Object Windows.Forms.Button
$btnHelp.Text      = '?'
$btnHelp.Location  = New-Object Drawing.Point(930, 24)
$btnHelp.Size      = New-Object Drawing.Size(36, 36)
$btnHelp.FlatStyle = 'Flat'
$btnHelp.BackColor = [Drawing.Color]::FromArgb(255, 25, 118, 210)
$btnHelp.ForeColor = [Drawing.Color]::White
$btnHelp.Font      = New-Object Drawing.Font('Segoe UI', 13, $bold)
$btnHelp.Anchor    = 'Top, Right'
$btnHelp.FlatAppearance.BorderSize           = 0
$btnHelp.FlatAppearance.MouseOverBackColor   = [Drawing.Color]::FromArgb(255, 42, 140, 240)
$gPath = New-Object Drawing.Drawing2D.GraphicsPath
$gPath.AddEllipse(0, 0, 35, 35)
$btnHelp.Region = New-Object Drawing.Region($gPath)

$btnHelp.Add_Click({
    $hw = New-Object Windows.Forms.Form
    $hw.Text            = 'SA WinTools - Help'
    $hw.Size            = New-Object Drawing.Size(700, 830)
    $hw.BackColor       = [Drawing.Color]::FromArgb(255, 5, 5, 5)
    $hw.StartPosition   = 'CenterScreen'
    $hw.FormBorderStyle = 'FixedDialog'
    $hw.MaximizeBox     = $false

    $hTitle = New-Object Windows.Forms.Label
    $hTitle.Text      = 'SA WinTools Professional'
    $hTitle.ForeColor = [Drawing.Color]::Cyan
    $hTitle.Font      = New-Object Drawing.Font('Segoe UI', 20, $bold)
    $hTitle.Location  = New-Object Drawing.Point(20, 18)
    $hTitle.AutoSize  = $true
    $hw.Controls.Add($hTitle)

    $hSub = New-Object Windows.Forms.Label
    $hSub.Text      = 'v20.10  |  ' + ([char]0x00A9) + ' 2026 Antoniou Stavros. AI-Assisted Development.'
    $hSub.ForeColor = [Drawing.Color]::FromArgb(255, 130, 130, 130)
    $hSub.Font      = New-Object Drawing.Font('Segoe UI', 9)
    $hSub.Location  = New-Object Drawing.Point(22, 58)
    $hSub.AutoSize  = $true
    $hw.Controls.Add($hSub)

    $rtb = New-Object Windows.Forms.RichTextBox
    $rtb.Location    = New-Object Drawing.Point(15, 85)
    $rtb.Size        = New-Object Drawing.Size(658, 680)
    $rtb.BackColor   = [Drawing.Color]::FromArgb(255, 14, 14, 14)
    $rtb.ForeColor   = [Drawing.Color]::White
    $rtb.Font        = New-Object Drawing.Font('Segoe UI', 10)
    $rtb.ReadOnly    = $true
    $rtb.BorderStyle = 'None'
    $rtb.ScrollBars  = 'Vertical'
    $hw.Controls.Add($rtb)

    $fBold = New-Object Drawing.Font('Segoe UI', 10, $bold)
    $fNorm = New-Object Drawing.Font('Segoe UI', 10)
    $fHead = New-Object Drawing.Font('Segoe UI', 11, $bold)
    $cCyan  = [Drawing.Color]::FromArgb(255,  0, 200, 220)
    $cWhite = [Drawing.Color]::White
    $cGray  = [Drawing.Color]::FromArgb(255, 170, 170, 170)
    $cDim   = [Drawing.Color]::FromArgb(255,  65,  65,  65)

    $addSection = {
        param($label)
        $rtb.SelectionFont  = $fHead; $rtb.SelectionColor = $cCyan
        $rtb.AppendText("`n  $label`n")
        $rtb.SelectionFont  = $fNorm; $rtb.SelectionColor = $cDim
        $rtb.AppendText('  ' + ('-' * 62) + "`n")
    }
    $addEntry = {
        param($name, $desc)
        $rtb.SelectionFont  = $fBold; $rtb.SelectionColor = $cWhite
        $rtb.AppendText("  $($name.PadRight(20))")
        $rtb.SelectionFont  = $fNorm; $rtb.SelectionColor = $cGray
        $rtb.AppendText("$desc`n")
    }

    & $addSection 'SYSTEM REPAIR'
    & $addEntry 'SFC Repair'        'Scans Windows files for damage and repairs them automatically.'
    & $addEntry 'DISM Clean'        'Clears leftover Windows update data to free up disk space.'
    & $addEntry 'DISM Repair'       'Downloads fresh Windows files from Microsoft to fix deep system issues.'
    & $addEntry 'Fix Win Update'    'Unsticks Windows Update when it stops working or gets stuck.'
    & $addEntry 'WinRE Manager'     'Checks that Windows Recovery mode is ready for emergency use.'

    & $addSection 'MAINTENANCE'
    & $addEntry 'Cleanup'           'Deletes junk files, temp data, and old logs to recover disk space.'
    & $addEntry 'Disk Analyzer'     'Shows drive usage and finds large files or folders taking up space.'
    & $addEntry 'Reset Spooler'     'Fixes print queue problems by restarting the print service.'
    & $addEntry 'Install/Uninstall' 'Scans and repairs broken entries stopping programs from installing.'
    & $addEntry 'Flush Network'     'Resets DNS cache, network settings, or IP config to fix connectivity.'

    & $addSection 'HARDWARE & DIAGNOSTICS'
    & $addEntry 'Trim SSD'          'Tells your SSD to clean up internally, keeping it fast and healthy.'
    & $addEntry 'Check HDD'         'Scans a hard drive for errors or schedules a repair on next startup.'
    & $addEntry 'Device Query'      'Lists installed drivers, USB/HID devices, or removes problem entries.'
    & $addEntry 'Services Check'    'Finds services set to run automatically that have unexpectedly stopped.'
    & $addEntry 'Event Errors'      'Shows recent system errors and crash history from Windows event logs.'

    & $addSection 'SYSTEM INFO & STATUS'
    & $addEntry 'Time Sync'         'Checks or forces Windows to sync its clock with the internet time server.'
    & $addEntry 'Activation'        'Shows license status, reactivates online, or installs a new product key.'
    & $addEntry 'Network Info'      'Shows IP addresses, full adapter details, DNS cache, connections, and MAC addresses.'
    & $addEntry 'Wi-Fi & Firewall'  'Shows Wi-Fi profiles and passwords, generates WLAN report, and controls the firewall.'
    & $addEntry 'Power & System'    'Shows full system specs, generates energy efficiency report, or battery health report.'

    & $addSection 'BOTTOM CONTROLS'
    & $addEntry 'Open Current Log'  'Opens the last operation output in Notepad for review or saving.'
    & $addEntry 'Clear'             'Stops any active task and clears the status and log display.'
    & $addEntry 'Stop All'          'Forces the current running operation to stop immediately.'
    & $addEntry 'Reboot'            'Restarts the computer after asking for confirmation.'

    $hFooter = New-Object Windows.Forms.Label
    $hFooter.Text      = ([char]0x00A9) + ' 2026 Antoniou Stavros. AI-Assisted Development. All rights reserved.'
    $hFooter.ForeColor = [Drawing.Color]::FromArgb(255, 75, 75, 75)
    $hFooter.Font      = New-Object Drawing.Font('Segoe UI', 8)
    $hFooter.Location  = New-Object Drawing.Point(([int]((700 - 450) / 2)), 775)
    $hFooter.AutoSize  = $true
    $hw.Controls.Add($hFooter)

    [void]$hw.ShowDialog()
})
$pHeader.Controls.Add($btnHelp)

# ============================================================
# LOAD BUTTON DEFINITIONS
# ============================================================
. $btnPath

# ============================================================
# SHOW
# ============================================================
[void]$f.ShowDialog()
