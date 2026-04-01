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
        public int type;
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
Write-Host '[PS] Launching Acrobat ...'
$proc = Start-Process -FilePath $acroExe -ArgumentList ('"' + $InputPdf + '"') -PassThru

# Wait for main window
$hwnd = [IntPtr]::Zero
$root = [System.Windows.Automation.AutomationElement]::RootElement

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 1000
    $candidates = Get-Process -Name 'Acrobat' -ErrorAction SilentlyContinue |
                  Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }
    if ($candidates) {
        $best = $null; $bestArea = 0; $bestWinRect = $null
        foreach ($cand in $candidates) {
            try {
                $cCond = New-Object System.Windows.Automation.PropertyCondition(
                    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $cand.Id)
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
            Write-Host ('[PS] Acrobat window: PID=' + $best.Id + ' rect=' +
                        [int]$bestWinRect.X + ',' + [int]$bestWinRect.Y +
                        ' ' + [int]$bestWinRect.Width + 'x' + [int]$bestWinRect.Height)
            break
        }
    }
}
if ($hwnd -eq [IntPtr]::Zero) { throw 'Acrobat window did not appear' }

Write-Host '[PS] Waiting for XFA engine init ...'
Start-Sleep -Milliseconds 6000

[Win32]::ShowWindow($hwnd, 3)      | Out-Null   # SW_MAXIMIZE
Start-Sleep -Milliseconds 1500
[Win32]::BringWindowToTop($hwnd)   | Out-Null
[Win32]::SetForegroundWindow($hwnd)| Out-Null
Start-Sleep -Milliseconds 1000

# ── 3. UIAutomation — find Validate button ────────────────────────────────────
Write-Host '[PS] Scanning UIAutomation tree for Validate button ...'
$pidCond = New-Object System.Windows.Automation.PropertyCondition(
               [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $proc.Id)
$topWins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCond)
$win = $null; $maxWinArea = 0
foreach ($tw in $topWins) {
    try {
        $twR = $tw.Current.BoundingRectangle
        $twA = $twR.Width * $twR.Height
        if ($twA -gt $maxWinArea) { $maxWinArea = $twA; $win = $tw }
    } catch { }
}

$pageViewRect = $null
$winBounds    = $null

if ($win) {
    $winBounds = $win.Current.BoundingRectangle
    $allElems  = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                     [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($el in $allElems) {
        try {
            if ($null -eq $pageViewRect -and $el.Current.Name -eq 'AVPageView') {
                $pageViewRect = $el.Current.BoundingRectangle
                Write-Host ('[PS] AVPageView: ' + [int]$pageViewRect.X + ',' + [int]$pageViewRect.Y +
                            ' ' + [int]$pageViewRect.Width + 'x' + [int]$pageViewRect.Height)
            }
        } catch { }
    }
}

# ── 4. Click document area → Tab → Space  (Validate is first tab item) ────────
$validated = $false

# Determine a safe click point inside the page canvas to give it keyboard focus
if ($null -ne $pageViewRect -and $pageViewRect.Width -gt 200) {
    $pvX = [int]$pageViewRect.X;  $pvY = [int]$pageViewRect.Y
    $pvW = [int]$pageViewRect.Width; $pvH = [int]$pageViewRect.Height
} elseif ($null -ne $winBounds -and $winBounds.Width -gt 800) {
    $pvX = [int]($winBounds.X + 440); $pvY = [int]($winBounds.Y + 153)
    $pvW = [int]($winBounds.Width - 460); $pvH = [int]($winBounds.Height - 200)
    Write-Host ('[PS] Estimated AVPageView: ' + $pvX + ',' + $pvY + ' ' + $pvW + 'x' + $pvH)
} else {
    throw 'Cannot determine page viewport coordinates'
}

# Click in the grey margin (left of page) to focus the document without landing on a field
$pageH_px = $pvH
$pageW_px = [int]($pageH_px * 0.7729)
$pageLeft = $pvX + [int](($pvW - $pageW_px) / 2)
$grayX    = $pvX + [int](($pageLeft - $pvX) / 2)
$grayY    = $pvY + 80
if ($grayX -le $pvX) { $grayX = $pvX + 10 }  # fallback if page fills viewport

# ── Click inside the page, then Tab to first XFA field (Validate) ─────────────
# COM (AcroExch.App) does not work when launched as a Java subprocess due to
# Windows session isolation. Clicking the grey margin only focuses AVPageView
# (the container pane) — Tab from there never enters XFA field navigation.
# Clicking INSIDE the white page content area activates the XFA form, and Tab
# then cycles through XFA fields in tab order (Validate is first).

$validated = $false

# Calculate center of the white page area
$pageH_px  = $pvH
$pageW_px  = [int]($pageH_px * 0.7729)   # letter portrait aspect
$pageLeft  = $pvX + [int](($pvW - $pageW_px) / 2)
$pageCentX = $pageLeft + [int]($pageW_px / 2)
$pageCentY = $pvY + [int]($pageH_px / 2)

Write-Host ('[PS] Page area  : left=' + $pageLeft + ' w=' + $pageW_px + ' top=' + $pvY + ' h=' + $pageH_px)
Write-Host ('[PS] Page center: (' + $pageCentX + ',' + $pageCentY + ')')

# Click page center — activates XFA form focus
[Win32]::SetForegroundWindow($hwnd) | Out-Null
[Win32]::Click($pageCentX, $pageCentY)
Start-Sleep -Milliseconds 800

# Escape — exit any field that may have been activated by the click
[Win32]::SetForegroundWindow($hwnd) | Out-Null
[System.Windows.Forms.SendKeys]::SendWait('{ESC}')
Start-Sleep -Milliseconds 400

# Ctrl+Home — move to document beginning so Tab starts from field 1
[Win32]::SetForegroundWindow($hwnd) | Out-Null
[System.Windows.Forms.SendKeys]::SendWait('^{HOME}')
Start-Sleep -Milliseconds 800

# ── Dump all UIAutomation elements Acrobat exposes ───────────────────────────
Write-Host '[PS] --- UIAutomation full element dump (all named elements) ---'
if ($win) {
    $allElems = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                    [System.Windows.Automation.Condition]::TrueCondition)
    $dumpCount = 0
    foreach ($el in $allElems) {
        try {
            $ename = $el.Current.Name
            $etype = $el.Current.ControlType.ProgrammaticName
            $eclass = $el.Current.ClassName
            if ($ename -and $ename.Trim() -ne '') {
                Write-Host ('  [UIA] ' + $etype + ' | name="' + $ename + '" | class="' + $eclass + '"')
                $dumpCount++
            }
        } catch { }
    }
    Write-Host ('[PS] Total named elements: ' + $dumpCount)
} else {
    Write-Host '[PS] No window found for UIA dump.'
}
Write-Host '[PS] --- End UIAutomation dump ---'

# ── Tab through 20 items and log what UIAutomation reports each time ──────────
Write-Host '[PS] --- Tab scan: pressing Tab 20 times, logging focused element ---'
for ($t = 1; $t -le 20; $t++) {
    [Win32]::SetForegroundWindow($hwnd) | Out-Null
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}')
    Start-Sleep -Milliseconds 400
    try {
        $f = [System.Windows.Automation.AutomationElement]::FocusedElement
        if ($f) {
            Write-Host ('[PS] Tab ' + $t + ': name="' + $f.Current.Name +
                        '" type=' + $f.Current.ControlType.ProgrammaticName +
                        ' class="' + $f.Current.ClassName + '"')
        } else {
            Write-Host ('[PS] Tab ' + $t + ': (no focused element reported)')
        }
    } catch {
        Write-Host ('[PS] Tab ' + $t + ': error - ' + $_.Exception.Message)
    }
}
Write-Host '[PS] --- End Tab scan ---'

$validated = $false

# ── 6. Save As ────────────────────────────────────────────────────────────────
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

if (Test-Path $OutputPdf) {
    Write-Host ('[PS] Saved: ' + [Math]::Round((Get-Item $OutputPdf).Length/1024,1) + ' KB')
} else {
    Write-Host '[PS] WARN: output file not found after save'
}

# ── 7. Close Acrobat ──────────────────────────────────────────────────────────
Write-Host '[PS] Closing Acrobat ...'
[Win32]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 300
[System.Windows.Forms.SendKeys]::SendWait('%{F4}')
Start-Sleep -Milliseconds 1500
[System.Windows.Forms.SendKeys]::SendWait('n')
Start-Sleep -Milliseconds 1000
Write-Host '[PS] Done.'
