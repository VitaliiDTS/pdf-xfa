package com.test;

import com.datalogics.PDFL.*;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.util.EnumSet;
import java.util.List;

/**
 * Mode "acrobat-headless" — same pipeline as AcrobatBarcodeStep but without
 * opening the Acrobat GUI window or doing any mouse/keyboard automation.
 *
 * Flow:
 *   1. Fill XFA form via importXFAFormsData() and save → acrobat_hl_filled.pdf
 *   2. Invoke scripts/acrobat_headless_barcodes.ps1 via PowerShell:
 *      - Creates AcroExch.App COM object WITHOUT calling .Show()
 *      - Opens PDF via AcroExch.PDDoc (no visible window)
 *      - Calls XFA JS barcode functions via GetJSObject().eval()
 *      - Saves → acrobat_hl_barcoded.pdf
 *   3. Re-open barcoded PDF with APDFL
 *   4. flattenXFAFormFieldsAsIfPrinted() → acrobat_hl_final.pdf
 *   5. inspectPageResources() to confirm Image XObjects (rendered PDF417 barcodes)
 */
public class AcrobatHeadlessStep {

    private static final String FILLED_PDF   = XfaFormFiller.BASE_DIR + "/output/acrobat_hl_filled.pdf";
    private static final String BARCODED_PDF = XfaFormFiller.BASE_DIR + "/output/acrobat_hl_barcoded.pdf";
    private static final String FINAL_PDF    = XfaFormFiller.BASE_DIR + "/output/acrobat_hl_final.pdf";
    private static final String PS_SCRIPT    = XfaFormFiller.BASE_DIR + "/scripts/acrobat_headless_barcodes.ps1";

    public static void run() throws Exception {
        // ── 0. License ────────────────────────────────────────────────────────
        String licenseKey = XfaFormFiller.env("APDFL_LICENSE_KEY", null);
        if (licenseKey != null && !licenseKey.isBlank()) {
            Library.setLicenseKey(licenseKey);
        }

        // ── 1. Library ────────────────────────────────────────────────────────
        String nativesDir = new File(System.getProperty("project.basedir",
                new File("").getAbsolutePath()), "target/natives").getAbsolutePath();
        Library lib = XfaFormFiller.initLibrary(nativesDir);
        lib.setAllowOpeningXFA(true);
        System.out.println("[INFO] AcrobatHeadlessStep ready.  APDFL: " + Library.getAPDFLVersion());

        try {
            File inputFile = new File(XfaFormFiller.INPUT_PDF);
            if (!inputFile.exists()) {
                System.err.println("[ERROR] Input PDF not found: " + inputFile.getAbsolutePath());
                return;
            }

            // ── 2. Kill leftover Acrobat processes ────────────────────────────
            killAcrobat();

            // ── 3. Fill XFA form and save (APDFL step) ────────────────────────
            System.out.println("\n[STEP 1/3] Fill form via importXFAFormsData → " + FILLED_PDF);
            Document doc = XfaFormFiller.openDocument(XfaFormFiller.INPUT_PDF);

            File xmlFile = new File(XfaFormFiller.INPUT_XML);
            if (xmlFile.exists()) {
                boolean ok = doc.importXFAFormsData(xmlFile.getAbsolutePath());
                System.out.println(ok ? "[OK]  Data imported." : "[WARN] Import returned false.");
            } else {
                System.err.println("[WARN] test_data.xml not found — saving unfilled form.");
            }

            new File(XfaFormFiller.BASE_DIR + "/output").mkdirs();
            doc.save(EnumSet.of(SaveFlags.FULL), FILLED_PDF);
            long filledSize = new File(FILLED_PDF).length();
            System.out.printf("[OK]  Saved filled PDF: %.1f KB%n", filledSize / 1024.0);
            doc.close();

            // ── 4. Acrobat COM headless step ──────────────────────────────────
            System.out.println("\n[STEP 2/3] Acrobat COM (hidden) → XFA JS barcode trigger → " + BARCODED_PDF);
            boolean psOk = runPowerShellScript(PS_SCRIPT, FILLED_PDF, BARCODED_PDF);
            if (!psOk || !new File(BARCODED_PDF).exists()) {
                System.err.println("[ERROR] Headless Acrobat step failed or output not produced.");
                System.err.println("        Ensure Adobe Acrobat Pro is installed.");
                return;
            }
            long barcodedSize = new File(BARCODED_PDF).length();
            System.out.printf("[OK]  Barcoded PDF: %.1f KB%n", barcodedSize / 1024.0);
            System.out.printf("      Size change: %+.1f KB%n", (barcodedSize - filledSize) / 1024.0);

            // ── 5. Re-open with APDFL and flatten ─────────────────────────────
            System.out.println("\n[STEP 3/3] APDFL flatten → " + FINAL_PDF);
            Document doc2 = XfaFormFiller.openDocument(BARCODED_PDF);
            System.out.println("[OK]  Re-opened.  Forms: " + doc2.getFormsType()
                    + "  isDynXFA: " + doc2.isDynamicXFA());

            if (doc2.isDynamicXFA() || doc2.isStaticXFA()) {
                long flattened = doc2.flattenXFAFormFieldsAsIfPrinted();
                System.out.println("[OK]  flattenXFAFormFieldsAsIfPrinted() — fields: " + flattened);
            } else {
                doc2.flattenAcroFormFields();
                System.out.println("[OK]  flattenAcroFormFields() done.");
            }

            doc2.save(EnumSet.of(SaveFlags.FULL), FINAL_PDF);
            long finalSize = new File(FINAL_PDF).length();
            System.out.printf("[OK]  Final flattened: %s  (%.1f KB)%n", FINAL_PDF, finalSize / 1024.0);

            System.out.println("[INFO] Forms type after flatten: " + doc2.getFormsType());
            FlattenTest.inspectPageResources(doc2);
            doc2.close();

        } catch (Exception e) {
            System.err.println("[ERROR] AcrobatHeadlessStep: " + e.getMessage());
            throw e;
        }
    }

    private static boolean runPowerShellScript(String scriptPath, String inputPdf, String outputPdf)
            throws Exception {
        String psExe = findPowerShell();
        System.out.println("[PS]  Executable : " + psExe);
        System.out.println("[PS]  Script     : " + scriptPath);

        ProcessBuilder pb = new ProcessBuilder(List.of(
                psExe,
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", new File(scriptPath).getAbsolutePath(),
                "-InputPdf",  new File(inputPdf).getAbsolutePath(),
                "-OutputPdf", new File(outputPdf).getAbsolutePath()
        ));
        pb.redirectErrorStream(true);
        pb.environment().put("PSModulePath", "");

        Process proc = pb.start();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(proc.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("  " + line);
            }
        }

        int exitCode = proc.waitFor();
        System.out.println("[PS]  Exit code: " + exitCode);
        return exitCode == 0;
    }

    private static void killAcrobat() {
        try {
            Process p = new ProcessBuilder("taskkill", "/F", "/IM", "Acrobat.exe")
                    .redirectErrorStream(true).start();
            String out = new String(p.getInputStream().readAllBytes()).trim();
            p.waitFor();
            if (!out.isEmpty()) System.out.println("[INFO] taskkill Acrobat: " + out);
        } catch (Exception e) {
            // non-fatal
        }
    }

    private static String findPowerShell() {
        // Acrobat is 32-bit — must use 32-bit PowerShell (SysWOW64) to create
        // AcroExch.App COM object; 64-bit PowerShell returns E_NOINTERFACE.
        String[] candidates = {
            "C:\\Windows\\SysWOW64\\WindowsPowerShell\\v1.0\\powershell.exe",
            "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            "C:\\Program Files\\PowerShell\\7\\pwsh.exe",
            "powershell.exe"
        };
        for (String c : candidates) {
            if (new File(c).exists()) return c;
        }
        return candidates[0];
    }
}
