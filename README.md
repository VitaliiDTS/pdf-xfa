# APDFL XFA Form Test — IMM 1294

Tests **Datalogics Adobe PDF Library (APDFL) 18.59.0 + Forms Extension**
against the encrypted dynamic XFA form *IMM 1294* (Canadian Study Permit).

---

## Prerequisites

| Tool | Check |
|------|-------|
| Java 17+ | `java -version` |
| Maven 3.8+ | `mvn -version` |
| Adobe Acrobat Pro DC | required for `acrobat` mode |
| APDFL + Forms Extension trial key | <https://www.datalogics.com/pdf-form-functions> |

> **Note:** APDFL and Forms Extension are activated with the same key from the link above.
> The key is entered interactively on first run and saved to `apdfl.lic` automatically.

---

## Quick start

### 1. Place the input PDF

```
input/IMM1294 - 2023.11 - CURRENT.pdf
```

PDF properties: AES-128 encrypted, empty password, dynamic XFA (LiveCycle Designer ES 10.0),
barcode fields PaperFormsBarcode1..5 (PDF417).

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```
APDFL_LICENSE_KEY=xxxx-xxxx-xxxx-xxxx
```

`.env` is loaded automatically on startup. Any variable already set in the shell
takes precedence over `.env`.

Available variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `APDFL_LICENSE_KEY` | *(demo mode)* | APDFL license key |
| `APDFL_INPUT_PDF` | `input/IMM1294 - 2023.11 - CURRENT.pdf` | Path to input PDF |
| `APDFL_INPUT_XML` | `src/main/resources/test_data.xml` | Path to XFA datasets XML |

### 3. Set JAVA_HOME (once)

If Maven complains about `JAVA_HOME not defined`, set it once in PowerShell:

```powershell
[System.Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Microsoft\jdk-17.0.13.11-hotspot", "User")
```

Restart the terminal after this.

### 4. First run — license activation

On first run the library will prompt for activation keys interactively.
Pipe the key twice (once for APDFL, once for Forms Extension):

```powershell
"YOUR-KEY`nYOUR-KEY`n" | mvn exec:exec "-Dexec.mode=fill"
```

After successful activation `apdfl.lic` is created and subsequent runs
no longer prompt for the key.

### 5. Run

> All commands must be run from the `apdfl-xfa-test/` directory (where `pom.xml` is).

```powershell
mvn exec:exec "-Dexec.mode=acrobat"
```

Press **Ctrl+C** in the terminal to stop at any time.

---

## Modes

| Mode | Command | Description |
|------|---------|-------------|
| `fill` | `mvn exec:exec "-Dexec.mode=fill"` | Fill XFA fields via APDFL, save PDF |
| `flatten` | `mvn exec:exec "-Dexec.mode=flatten"` | Fill + flatten via Forms Extension |
| `barcode` | `mvn exec:exec "-Dexec.mode=barcode"` | Pre-compute barcode strings, inject via XFA datasets |
| `acrobat` | `mvn exec:exec "-Dexec.mode=acrobat"` | Full pipeline with Acrobat GUI automation |
| `acrobat-headless` | `mvn exec:exec "-Dexec.mode=acrobat-headless"` | Full pipeline via Acrobat COM API (see limitations) |
| `all` | `mvn exec:exec` | Runs fill + flatten + barcode |

### Pipeline: `acrobat` (recommended)

```
[STEP 1/3]  APDFL: fill XFA fields → output/acrobat_filled.pdf
[STEP 2/3]  Acrobat opens visibly, GUI automation clicks "Validate" → output/acrobat_barcoded.pdf
[STEP 3/3]  APDFL: flattenXFAFormFieldsAsIfPrinted() → output/acrobat_final_flattened.pdf
```

**Important:** during STEP 2 Acrobat opens on screen and the mouse is controlled
automatically. Do not touch the mouse or keyboard until the process finishes (~3-5 min).
Press **Ctrl+C** to abort.

### Pipeline: `acrobat-headless`

Same as `acrobat` but attempts to use Acrobat COM API without showing the window.

**Known limitation:** when launched as a Java subprocess, Acrobat COM (`AcroExch.App`,
`AcroExch.PDDoc`) fails with `E_NOINTERFACE` due to Windows session isolation —
the subprocess does not have access to the interactive desktop session required
by Acrobat's out-of-process COM server. Use `acrobat` mode instead.

---

## Output files

| File | Produced by |
|------|-------------|
| `output/filled_result.pdf` | `fill` |
| `output/flattened_result.pdf` | `flatten` |
| `output/barcode_inject_result.pdf` | `barcode` |
| `output/acrobat_filled.pdf` | `acrobat` step 1 |
| `output/acrobat_barcoded.pdf` | `acrobat` step 2 — with PDF417 barcodes |
| `output/acrobat_final_flattened.pdf` | `acrobat` step 3 — final static PDF |
| `output/acrobat_hl_filled.pdf` | `acrobat-headless` step 1 |
| `output/acrobat_hl_barcoded.pdf` | `acrobat-headless` step 2 |
| `output/acrobat_hl_final.pdf` | `acrobat-headless` step 3 |

Open `acrobat_final_flattened.pdf` in Adobe Reader to verify PDF417 barcodes.

---

## Project structure

```
apdfl-xfa-test/
├── .env                          ← local config (not committed)
├── .env.example                  ← template to copy
├── .gitignore
├── pom.xml
├── input/
│   └── IMM1294 - 2023.11 - CURRENT.pdf   ← place here (not committed)
├── output/                       ← generated files (not committed)
├── scripts/
│   ├── acrobat_trigger_barcodes.ps1       ← GUI automation (acrobat mode)
│   └── acrobat_headless_barcodes.ps1      ← COM headless  (acrobat-headless mode)
└── src/main/
    ├── java/com/test/
    │   ├── Main.java                 entry point + .env loader
    │   ├── XfaFormFiller.java        fill + save (env var resolution)
    │   ├── FlattenTest.java          fill + flatten
    │   ├── BarcodeTest.java          barcode string injection
    │   ├── AcrobatBarcodeStep.java   acrobat GUI pipeline
    │   ├── AcrobatHeadlessStep.java  acrobat headless pipeline
    │   ├── BarcodeEncoder.java       computes pipe-delimited barcode strings
    │   └── FormData.java             form field data model
    └── resources/
        └── test_data.xml             XFA datasets XML (sample data)
```

---

## Known issues

### Barcodes missing after `fill` / `flatten` / `barcode`

APDFL does not execute XFA JavaScript. `BC.encodeAll()` — the function that
computes PDF417 barcode values — only runs inside Acrobat's XFA engine.
Use `acrobat` mode for actual barcode generation.

### `acrobat` — Validate button not found

The script scans up to 5 pages clicking a 4×8 coordinate grid and waits for
the page count to increase (sign that barcode page was generated). If the button
position changes with a different Acrobat version or screen resolution, the
coordinate grid may miss it. In that case open the PDF manually in Acrobat and
click Validate to see where it is.

### `acrobat-headless` — E_NOINTERFACE

See pipeline description above. Use `acrobat` mode instead.

### License activation — Error -1

APDFL and Forms Extension are **separate** products with separate trial keys.
If `forms_extension` activation fails with `Error -1`:
- Request a Forms Extension trial at <https://www.datalogics.com/pdf-form-functions>
- Or contact EvalSupport@Datalogics.com

### Forms Extension not found in Maven Central

```bash
mvn install:install-file \
  -Dfile=FormsExtension.jar \
  -DgroupId=com.datalogics.pdfl \
  -DartifactId=forms-extension \
  -Dversion=local \
  -Dpackaging=jar
```

Then set `<apdfl.version>local</apdfl.version>` in `pom.xml`.
