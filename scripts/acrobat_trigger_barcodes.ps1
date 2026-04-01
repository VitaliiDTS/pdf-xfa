param(
    [Parameter(Mandatory=$true)] [string]$InputPdf,
    [Parameter(Mandatory=$true)] [string]$OutputPdf
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);
    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT {
        public int type; // 0=MOUSE
        public MOUSEINPUT mi;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT {
        public int dx, dy, mouseData, dwFlags, time;
        public IntPtr dwExtraInfo;
    }
    public static void Click(int x, int y) {
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(50);
        var inputs = new INPUT[2];
        // MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
        // MOUSEEVENTF_ABSOLUTE = 0x8000, MOUSEEVENTF_MOVE = 0x0001 — use 0 for relative no-move
        inputs[0].type = 0; inputs[0].mi.dwFlags = 0x0002;
        inputs[1].type = 0; inputs[1].mi.dwFlags = 0x0004;
        SendInput(2, inputs, System.Runtime.InteropServices.Marshal.SizeOf(typeof(INPUT)));
        System.Threading.Thread.Sleep(80);
    }
}
'@

$InputPdf  = [System.IO.Path]::GetFullPath($InputPdf)
$OutputPdf = [System.IO.Path]::GetFullPath($OutputPdf)
Write-Host '[PS] Input  :' $InputPdf
Write-Host '[PS] Output :' $OutputPdf
if (-not (Test-Path $InputPdf)) { throw ('Input PDF not found: ' + $InputPdf) }

# ── 1. Find Acrobat exe ───────────────────────────────────────────────────────
$acroExe = $null
foreach ($rp in @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Acrobat.exe',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Acrobat.exe')) {
    if (Test-Path $rp) { $acroExe = (Get-ItemProperty $rp).'(Default)'; break }
}
if (-not $acroExe -or -not (Test-Path $acroExe)) {
    foreach ($c in @(
        'C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe',
        'C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe')) {
        if (Test-Path $c) { $acroExe = $c; break }
    }
}
if (-not $acroExe) { throw 'Adobe Acrobat not found' }
Write-Host '[PS] Acrobat exe:' $acroExe

# ── 2. Launch Acrobat ─────────────────────────────────────────────────────────
Write-Host '[PS] Launching Acrobat with PDF ...'
$proc = Start-Process -FilePath $acroExe -ArgumentList ('"' + $InputPdf + '"') -PassThru

# Wait for main window — pick the LARGEST Acrobat window (avoids picking helper processes)
$hwnd = [IntPtr]::Zero
$root = [System.Windows.Automation.AutomationElement]::RootElement

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 1000
    # Search ALL running Acrobat processes and find the one with the biggest window
    $candidates = Get-Process -Name 'Acrobat' -ErrorAction SilentlyContinue |
                  Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }
    if ($candidates) {
        $best = $null; $bestArea = 0; $bestWinRect = $null
        foreach ($cand in $candidates) {
            try {
                $cCond = New-Object System.Windows.Automation.PropertyCondition(
                    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $cand.Id)
                # FindAll to get ALL top-level windows for this PID, pick the largest
                $cWins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cCond)
                foreach ($cw in $cWins) {
                    try {
                        $cR = $cw.Current.BoundingRectangle
                        $area = $cR.Width * $cR.Height
                        if ($area -gt $bestArea) { $bestArea = $area; $best = $cand; $bestWinRect = $cR }
                    } catch { }
                }
            } catch { }
        }
        if ($null -ne $best -and $bestArea -gt 100000) {
            $proc = $best; $hwnd = $best.MainWindowHandle
            Write-Host ('[PS] Largest Acrobat window after ' + ($i+1) + ' s: PID=' +
                        $best.Id + ' area=' + $bestArea + ' HWND=' + $hwnd +
                        ' rect=' + [int]$bestWinRect.X + ',' + [int]$bestWinRect.Y +
                        ' ' + [int]$bestWinRect.Width + 'x' + [int]$bestWinRect.Height)
            break
        }
    }
}
if ($hwnd -eq [IntPtr]::Zero) { throw 'Acrobat window did not appear' }

# Wait for XFA engine init
Write-Host '[PS] Waiting for XFA engine init ...'
Start-Sleep -Milliseconds 6000

[Win32]::ShowWindow($hwnd, 3)      | Out-Null   # SW_MAXIMIZE
Start-Sleep -Milliseconds 1500
[Win32]::BringWindowToTop($hwnd)   | Out-Null
[Win32]::SetForegroundWindow($hwnd)| Out-Null
Start-Sleep -Milliseconds 1000

# ── 3. UIAutomation scan ──────────────────────────────────────────────────────
Write-Host '[PS] Scanning UIAutomation tree ...'
$pidCond = New-Object System.Windows.Automation.PropertyCondition(
               [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $proc.Id)
# FindAll top-level windows for this PID and pick the largest (avoids helper windows)
$topWins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCond)
$win = $null; $maxWinArea = 0
foreach ($tw in $topWins) {
    try {
        $twR = $tw.Current.BoundingRectangle
        $twA = $twR.Width * $twR.Height
        if ($twA -gt $maxWinArea) { $maxWinArea = $twA; $win = $tw }
    } catch { }
}

$validateBtn  = $null
$pageViewRect = $null
$winBounds    = $null

if ($win) {
    $winBounds = $win.Current.BoundingRectangle
    Write-Host ('[PS] Window bounds: ' + [int]$winBounds.X + ',' + [int]$winBounds.Y +
                ' ' + [int]$winBounds.Width + 'x' + [int]$winBounds.Height)

    $allElems = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                    [System.Windows.Automation.Condition]::TrueCondition)
    $scanned = 0
    foreach ($el in $allElems) {
        try {
            $name = $el.Current.Name
            $ct   = $el.Current.ControlType.ProgrammaticName
            $r    = $el.Current.BoundingRectangle
            if ($name -and $scanned -lt 30) {
                Write-Host ('  [' + $scanned + '] ' + $ct + ' | ' + $name +
                            ' | rect=' + [int]$r.X + ',' + [int]$r.Y +
                            ' ' + [int]$r.Width + 'x' + [int]$r.Height)
                $scanned++
            }
            if ($name -match '(?i)validat|valider') {
                $validateBtn = $el
                Write-Host ('[PS] *** Validate button found: "' + $name + '"')
            }
            # AVPageView = real rendering viewport
            if ($null -eq $pageViewRect -and $name -eq 'AVPageView') {
                $pageViewRect = $r
                Write-Host ('[PS] AVPageView: ' + [int]$r.X + ',' + [int]$r.Y +
                            ' ' + [int]$r.Width + 'x' + [int]$r.Height)
            }
        } catch { }
    }
    Write-Host ('[PS] Total elements: ' + @($allElems).Count)
}

# ── 4. Click Validate if UIAutomation found it ────────────────────────────────
$barcodeGenerated = $false

if ($validateBtn) {
    Write-Host '[PS] Invoking Validate button via UIAutomation ...'
    try {
        $inv = $validateBtn.GetCurrentPattern(
                   [System.Windows.Automation.InvokePattern]::Pattern)
        $inv.Invoke()
        $barcodeGenerated = $true
    } catch {
        $rect = $validateBtn.Current.BoundingRectangle
        $cx   = [int]($rect.X + $rect.Width / 2)
        $cy   = [int]($rect.Y + $rect.Height / 2)
        [Win32]::Click($cx, $cy)
        $barcodeGenerated = $true
    }
    Start-Sleep -Milliseconds 8000
}

# ── 5. Coordinate-based click ─────────────────────────────────────────────────
if (-not $barcodeGenerated) {
    Write-Host '[PS] Switching to coordinate-based click.'

    # ── 5a. Connect via COM (New-Object works; GetActiveObject does not) ──────
    $acroApp = $null
    Write-Host '[PS] Connecting to Acrobat COM ...'
    for ($ri = 0; $ri -lt 10; $ri++) {
        try {
            $acroApp = New-Object -ComObject 'AcroExch.App'
            $acroApp.Show() | Out-Null
            Write-Host ('[PS] COM ready after ' + ($ri*2) + ' s')
            break
        } catch {
            Start-Sleep -Milliseconds 2000
        }
    }

    # ── 5b. Navigate to page 4 ────────────────────────────────────────────────
    if ($null -ne $acroApp) {
        try {
            $avDoc = $acroApp.GetActiveDoc()
            $pdDoc = $avDoc.GetPDDoc()
            $totalPg = $pdDoc.GetNumPages()
            Write-Host ('[PS] Total pages: ' + $totalPg)

            $targetPg = [Math]::Min(3, $totalPg - 1)   # 0-based, prefer page 4

            # Try navigation via JSObject.gotoPage (standard AcroJS method)
            $navOk = $false
            try {
                $jso = $pdDoc.GetJSObject()
                Write-Host ('[PS] Got JSObject. Trying gotoPage(' + $targetPg + ') ...')
                $jso.gotoPage($targetPg)
                [Win32]::SetForegroundWindow($hwnd) | Out-Null
                Start-Sleep -Milliseconds 1500
                Write-Host ('[PS] Navigated to page ' + ($targetPg+1) + ' via JSObject.gotoPage')
                $navOk = $true
            } catch {
                Write-Host ('[PS] JSObject.gotoPage(' + $targetPg + ') failed: ' + $_.Exception.Message)
            }

            # Try AVDoc.GetAVPageView().GotoPage
            if (-not $navOk) {
                try {
                    $avPV = $avDoc.GetAVPageView()
                    Write-Host ('[PS] Got AVPageView. Trying GotoPage(' + $targetPg + ') ...')
                    $avPV.GotoPage($targetPg)
                    [Win32]::SetForegroundWindow($hwnd) | Out-Null
                    Start-Sleep -Milliseconds 1500
                    Write-Host ('[PS] Navigated via AVPageView.GotoPage')
                    $navOk = $true
                } catch {
                    Write-Host ('[PS] AVPageView.GotoPage failed: ' + $_.Exception.Message)
                }
            }

            # Keyboard navigation: go to page 1 (Ctrl+Home)
            if (-not $navOk) {
                Write-Host '[PS] Navigating to page 1 via Ctrl+Home ...'
                [Win32]::SetForegroundWindow($hwnd) | Out-Null
                Start-Sleep -Milliseconds 500
                [System.Windows.Forms.SendKeys]::SendWait('^{HOME}')
                Start-Sleep -Milliseconds 1000
                $navOk = $true
                Write-Host '[PS] Navigated to page 1'
            }
        } catch {
            Write-Host ('[PS] COM navigation error: ' + $_.Exception.Message)
            # Still go to page 1 via keyboard
            [Win32]::SetForegroundWindow($hwnd) | Out-Null
            [System.Windows.Forms.SendKeys]::SendWait('^{HOME}')
            Start-Sleep -Milliseconds 1000
        }
    }

    # ── 5c. Fit Page zoom for consistent page layout ──────────────────────────
    Write-Host '[PS] Setting Fit Page zoom (Ctrl+0) ...'
    [Win32]::SetForegroundWindow($hwnd) | Out-Null
    [System.Windows.Forms.SendKeys]::SendWait('^0')
    Start-Sleep -Milliseconds 1500

    # ── 5d. Determine AVPageView coordinates ─────────────────────────────────
    if ($null -ne $pageViewRect -and $pageViewRect.Width -gt 200) {
        $pvX = [int]$pageViewRect.X
        $pvY = [int]$pageViewRect.Y
        $pvW = [int]$pageViewRect.Width
        $pvH = [int]$pageViewRect.Height
    } elseif ($null -ne $bestWinRect -and $bestWinRect.Width -gt 800) {
        $pvX = [int]($bestWinRect.X + 440)
        $pvY = [int]($bestWinRect.Y + 153)
        $pvW = [int]($bestWinRect.Width  - 460)
        $pvH = [int]($bestWinRect.Height - 200)
        Write-Host ('[PS] Using estimated AVPageView: ' + $pvX + ',' + $pvY + ' ' + $pvW + 'x' + $pvH)
    } else {
        throw 'Cannot determine page viewport coordinates'
    }

    # Letter page geometry at Fit-Page (single page, portrait)
    $pageH_px = $pvH
    $pageW_px = [int]($pageH_px * 0.7729)
    $pageLeft = $pvX + [int](($pvW - $pageW_px) / 2)
    Write-Host ('[PS] Page area: left=' + $pageLeft + ' w=' + $pageW_px +
                ' top=' + $pvY + ' h=' + $pageH_px)

    # Gray area (left of page) — click here to give the document focus without
    # landing inside a form field (which might move focus away from the page)
    $grayX = $pvX + [int](($pageLeft - $pvX) / 2)
    $grayY = $pvY + 80
    Write-Host ('[PS] Focus click at gray area (' + $grayX + ',' + $grayY + ')')
    [Win32]::SetForegroundWindow($hwnd) | Out-Null
    [Win32]::Click($grayX, $grayY)
    Start-Sleep -Milliseconds 800

    # ── 5e. COM page-count helper ─────────────────────────────────────────────
    function Get-PageCount {
        if ($null -eq $acroApp) { return -1 }
        try {
            $d = $acroApp.GetActiveDoc()
            if ($d) { $pd = $d.GetPDDoc(); if ($pd) { return $pd.GetNumPages() } }
        } catch { }
        return -1
    }

    # ── 5f. Scan ALL pages for Validate button ────────────────────────────────
    # Coarse 4x8 grid per page = 32 clicks per page × 5 pages = 160 max clicks
    # Wait 2s per click — total worst case ~5 min
    $xSteps = @(0.25, 0.50, 0.75, 0.90)
    $ySteps = @(0.06, 0.12, 0.20, 0.30, 0.40, 0.55, 0.70, 0.85)
    $totalPages = if ($null -ne $acroApp) { (Get-PageCount) } else { 5 }
    if ($totalPages -le 0) { $totalPages = 5 }

    :pageLoop for ($pageIdx = 0; $pageIdx -lt $totalPages -and -not $barcodeGenerated; $pageIdx++) {
        Write-Host ('[PS] --- Scanning page ' + ($pageIdx+1) + '/' + $totalPages + ' ---')

        # Navigate: page 1 is already current; advance with Ctrl+PageDown for subsequent
        if ($pageIdx -gt 0) {
            [Win32]::SetForegroundWindow($hwnd) | Out-Null
            [System.Windows.Forms.SendKeys]::SendWait('^{PGDN}')
            Start-Sleep -Milliseconds 1500
        }

        :clickLoop foreach ($yr in $ySteps) {
            foreach ($xr in $xSteps) {
                $cx = $pageLeft + [int]($pageW_px * $xr)
                $cy = $pvY      + [int]($pageH_px * $yr)
                Write-Host ('[PS] p' + ($pageIdx+1) + ' x=' + $xr + ' y=' + $yr + ' -> (' + $cx + ',' + $cy + ')')
                [Win32]::SetForegroundWindow($hwnd) | Out-Null
                [Win32]::Click($cx, $cy)
                Start-Sleep -Milliseconds 2000

                $pg = Get-PageCount
                if ($pg -ge 6) {
                    Write-Host '[PS] *** Barcode page generated! page count=' + $pg + ' ***'
                    $barcodeGenerated = $true
                    break pageLoop
                }
            }
        }
    }

    if (-not $barcodeGenerated) {
        Write-Host '[PS] WARN: Validate button not triggered after scanning all pages.'
    }
}

# ── 6. Wait for barcode rendering ─────────────────────────────────────────────
Write-Host '[PS] Waiting for barcode rendering ...'
Start-Sleep -Milliseconds 4000

# ── 7. Save As ────────────────────────────────────────────────────────────────
Write-Host '[PS] Saving via Ctrl+Shift+S ...'
[Win32]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait('^+s')
Start-Sleep -Milliseconds 2000
[System.Windows.Forms.SendKeys]::SendWait($OutputPdf)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Milliseconds 2000
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Milliseconds 1500

if (-not (Test-Path $OutputPdf)) {
    Write-Host '[PS] WARN: output not at expected path; trying COM fallback save ...'
    try { (New-Object -ComObject 'AcroExch.PDDoc').Save(1, $OutputPdf) | Out-Null } catch { }
}
if (Test-Path $OutputPdf) {
    Write-Host ('[PS] Output OK: ' + [Math]::Round((Get-Item $OutputPdf).Length/1024,1) + ' KB')
} else {
    Write-Host '[PS] WARN: output file not found'
}

# ── 8. Close Acrobat ──────────────────────────────────────────────────────────
Write-Host '[PS] Closing Acrobat ...'
[Win32]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 300
[System.Windows.Forms.SendKeys]::SendWait('%{F4}')
Start-Sleep -Milliseconds 1500
[System.Windows.Forms.SendKeys]::SendWait('n')
Start-Sleep -Milliseconds 1000
Write-Host '[PS] Done.'
