package com.test;

import com.datalogics.PDFL.*;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.util.EnumSet;
import java.util.List;

/**
 * Fill XFA form via APDFL, open in Acrobat, click Validate via PyAutoGUI, save.
 *
 * Flow:
 *   1. importXFAFormsData() → output/validate_filled.pdf
 *   2. Python: open in Acrobat, image-match Validate button, click, save → output/validate_result.pdf
 */
public class AcrobatValidateStep {

    private static final String OUTPUT_DIR   = XfaFormFiller.OUTPUT_DIR;
    private static final String FILLED_PDF  = OUTPUT_DIR + "/validate_filled.pdf";
    private static final String RESULT_PDF  = OUTPUT_DIR + "/validate_result.pdf";
    private static final String PY_SCRIPT   = XfaFormFiller.BASE_DIR + "/scripts/acrobat_validate.py";
    private static final String BUTTON_IMG  = XfaFormFiller.BASE_DIR + "/" + XfaFormFiller.FORM_DIR + "/button.png";

    public static void run() throws Exception {
        String licenseKey = XfaFormFiller.env("APDFL_LICENSE_KEY", null);
        if (licenseKey != null && !licenseKey.isBlank()) {
            Library.setLicenseKey(licenseKey);
        }

        String nativesDir = new File(System.getProperty("project.basedir",
                new File("").getAbsolutePath()), "target/natives").getAbsolutePath();
        Library lib = XfaFormFiller.initLibrary(nativesDir);
        lib.setAllowOpeningXFA(true);
        System.out.println("[INFO] AcrobatValidateStep ready.  APDFL: " + Library.getAPDFLVersion());

        try {
            File inputFile = new File(XfaFormFiller.INPUT_PDF);
            if (!inputFile.exists()) {
                System.err.println("[ERROR] Input PDF not found: " + inputFile.getAbsolutePath());
                return;
            }

            // Kill any leftover Acrobat
            killAcrobat();

            // ── 1. Fill XFA form ──────────────────────────────────────────────
            System.out.println("\n[STEP 1/2] Fill XFA form → " + FILLED_PDF);
            Document doc = XfaFormFiller.openDocument(XfaFormFiller.INPUT_PDF);

            File xmlFile = new File(XfaFormFiller.INPUT_XML);
            if (xmlFile.exists()) {
                boolean ok = doc.importXFAFormsData(xmlFile.getAbsolutePath());
                System.out.println(ok ? "[OK]  Data imported." : "[WARN] Import returned false.");
            } else {
                System.err.println("[WARN] test_data.xml not found — saving unfilled form.");
            }

            new File(OUTPUT_DIR).mkdirs();
            doc.save(EnumSet.of(SaveFlags.FULL), FILLED_PDF);
            System.out.printf("[OK]  Filled PDF saved: %.1f KB%n", new File(FILLED_PDF).length() / 1024.0);
            doc.close();

            // ── 2. Acrobat: open, click Validate, save ────────────────────────
            System.out.println("\n[STEP 2/2] Acrobat: open → Validate → save → " + RESULT_PDF);
            boolean psOk = runPythonScript(PY_SCRIPT, FILLED_PDF, RESULT_PDF, BUTTON_IMG);

            if (new File(RESULT_PDF).exists()) {
                System.out.printf("[OK]  Result: %s  (%.1f KB)%n",
                        RESULT_PDF, new File(RESULT_PDF).length() / 1024.0);
            } else {
                System.err.println("[WARN] Result PDF not produced. Check Acrobat output above.");
            }

            if (!psOk) {
                System.err.println("[WARN] Python script exited with non-zero code.");
            }

        } catch (Exception e) {
            System.err.println("[ERROR] AcrobatValidateStep: " + e.getMessage());
            throw e;
        }
        // lib.delete() omitted — XFA cleanup DEP issue
    }

    private static boolean runPythonScript(String scriptPath, String inputPdf, String outputPdf,
                                            String buttonImg) throws Exception {
        String pyExe = findPython();
        System.out.println("[PY]  Executable  : " + pyExe);
        System.out.println("[PY]  Script      : " + scriptPath);
        System.out.println("[PY]  Button image: " + buttonImg);

        ProcessBuilder pb = new ProcessBuilder(List.of(
                pyExe,
                new File(scriptPath).getAbsolutePath(),
                new File(inputPdf).getAbsolutePath(),
                new File(outputPdf).getAbsolutePath(),
                "--button-image", new File(buttonImg).getAbsolutePath()
        ));
        pb.redirectErrorStream(true);
        pb.environment().put("PYTHONIOENCODING", "utf-8");

        Process proc = pb.start();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(proc.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("  " + line);
            }
        }
        int exitCode = proc.waitFor();
        System.out.println("[PY]  Exit code: " + exitCode);
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

    private static String findPython() {
        for (String c : new String[]{"python", "py"}) {
            try {
                if (new ProcessBuilder(c, "--version").start().waitFor() == 0) return c;
            } catch (Exception ignored) {}
        }
        throw new RuntimeException("Python not found on PATH. Install Python and ensure it is on PATH.");
    }
}
