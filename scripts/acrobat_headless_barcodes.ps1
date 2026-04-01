param(
    [Parameter(Mandatory=$true)] [string]$InputPdf,
    [Parameter(Mandatory=$true)] [string]$OutputPdf
)

$ErrorActionPreference = 'Stop'
$InputPdf  = [System.IO.Path]::GetFullPath($InputPdf)
$OutputPdf = [System.IO.Path]::GetFullPath($OutputPdf)
Write-Host '[PS-HL] Input  :' $InputPdf
Write-Host '[PS-HL] Output :' $OutputPdf
if (-not (Test-Path $InputPdf)) { throw ('Input PDF not found: ' + $InputPdf) }

# ── 1. Connect to Acrobat COM (no visible window) ────────────────────────────
# Try AcroExch.App first; if E_NOINTERFACE (Reader or COM restriction), fall
# back to AcroExch.PDDoc standalone — it can open files and run JS without App.
Write-Host '[PS-HL] Connecting to Acrobat COM (hidden) ...'
$app = $null
try {
    $app = New-Object -ComObject 'AcroExch.App'
    Write-Host '[PS-HL] AcroExch.App created.'
} catch {
    Write-Host ('[PS-HL] AcroExch.App unavailable: ' + $_.Exception.Message)
    Write-Host '[PS-HL] Continuing with AcroExch.PDDoc standalone ...'
}

# ── 2. Open PDF via PDDoc ────────────────────────────────────────────────────
Write-Host '[PS-HL] Opening PDF via AcroExch.PDDoc ...'
$pdDoc = New-Object -ComObject 'AcroExch.PDDoc'
if ($null -ne $app) { $app.Show() | Out-Null; Start-Sleep -Milliseconds 1000 }
$opened = $pdDoc.Open($InputPdf)
if (-not $opened) { throw ('PDDoc.Open() returned false for: ' + $InputPdf) }
Write-Host '[PS-HL] PDF opened.'

$pagesBefore = $pdDoc.GetNumPages()
Write-Host ('[PS-HL] Pages before: ' + $pagesBefore)

# ── 3. Get JSObject and execute XFA barcode JS ───────────────────────────────
Write-Host '[PS-HL] Getting JSObject ...'
$jso = $null
try {
    $jso = $pdDoc.GetJSObject()
    Write-Host '[PS-HL] JSObject obtained.'
} catch {
    Write-Host ('[PS-HL] GetJSObject() failed: ' + $_.Exception.Message)
}

$barcodeTriggered = $false

if ($null -ne $jso) {
    # Attempt A: XFA BC.encodeAll() — standard XFA barcode API
    Write-Host '[PS-HL] Trying BC.encodeAll() ...'
    try {
        $jso.eval('BC.encodeAll()')
        Write-Host '[PS-HL] BC.encodeAll() executed.'
        $barcodeTriggered = $true
    } catch {
        Write-Host ('[PS-HL] BC.encodeAll() failed: ' + $_.Exception.Message)
    }

    # Attempt B: execValidate on the form
    if (-not $barcodeTriggered) {
        Write-Host '[PS-HL] Trying xfa.form.execValidate() ...'
        try {
            $jso.eval('xfa.form.execValidate()')
            Write-Host '[PS-HL] execValidate() executed.'
            $barcodeTriggered = $true
        } catch {
            Write-Host ('[PS-HL] execValidate() failed: ' + $_.Exception.Message)
        }
    }

    # Attempt C: execCalculate on the form
    if (-not $barcodeTriggered) {
        Write-Host '[PS-HL] Trying xfa.form.execCalculate() ...'
        try {
            $jso.eval('xfa.form.execCalculate()')
            Write-Host '[PS-HL] execCalculate() executed.'
            $barcodeTriggered = $true
        } catch {
            Write-Host ('[PS-HL] execCalculate() failed: ' + $_.Exception.Message)
        }
    }

    # Attempt D: click the validate button programmatically via JS
    if (-not $barcodeTriggered) {
        Write-Host '[PS-HL] Trying to find and click Validate button via JS ...'
        try {
            $clickJs = @'
(function() {
    var fields = this.getField("");
    // Try known IMM1294 validate button names
    var candidates = ["ValidationButton", "ValidateButton", "Validate",
                      "Page1.ValidationButton", "Page4.ValidationButton",
                      "form1.Page1.ValidationButton"];
    for (var i = 0; i < candidates.length; i++) {
        try {
            var f = this.getField(candidates[i]);
            if (f) { f.buttonImportIcon(); return "clicked:" + candidates[i]; }
        } catch(e) {}
    }
    return "not-found";
})()
'@
            $result = $jso.eval($clickJs)
            Write-Host ('[PS-HL] Button search result: ' + $result)
        } catch {
            Write-Host ('[PS-HL] Button click via JS failed: ' + $_.Exception.Message)
        }
    }

    # Attempt E: call app.execMenuItem for validation
    if (-not $barcodeTriggered) {
        Write-Host '[PS-HL] Trying app.execMenuItem("AcroForm:ValidateFields") ...'
        try {
            $jso.eval('app.execMenuItem("AcroForm:ValidateFields")')
            Write-Host '[PS-HL] execMenuItem executed.'
        } catch {
            Write-Host ('[PS-HL] execMenuItem failed: ' + $_.Exception.Message)
        }
    }

    # Short wait for XFA engine to process
    Start-Sleep -Milliseconds 3000
}

# ── 4. Check page count change ────────────────────────────────────────────────
$pagesAfter = $pdDoc.GetNumPages()
Write-Host ('[PS-HL] Pages after JS execution: ' + $pagesAfter)
if ($pagesAfter -gt $pagesBefore) {
    Write-Host ('[PS-HL] *** Page count increased from ' + $pagesBefore + ' to ' + $pagesAfter + ' — barcode page generated!')
} else {
    Write-Host '[PS-HL] WARN: Page count did not change — barcode generation may not have fired.'
}

# ── 5. Save ───────────────────────────────────────────────────────────────────
Write-Host ('[PS-HL] Saving -> ' + $OutputPdf)
$saveResult = $pdDoc.Save(1, $OutputPdf)   # 1 = PDSaveFull
if ($saveResult) {
    Write-Host ('[PS-HL] Saved OK: ' + [Math]::Round((Get-Item $OutputPdf -ErrorAction SilentlyContinue).Length/1024, 1) + ' KB')
} else {
    Write-Host '[PS-HL] WARN: Save() returned false.'
}

# ── 6. Cleanup ────────────────────────────────────────────────────────────────
try { $pdDoc.Close(0) } catch { }
try {
    if ($null -ne $jso)  { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($jso)   | Out-Null }
    if ($null -ne $pdDoc){ [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pdDoc) | Out-Null }
    if ($null -ne $app)  { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)   | Out-Null }
} catch { }
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()

Write-Host '[PS-HL] Done.'
