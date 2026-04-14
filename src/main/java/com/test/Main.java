package com.test;

import java.io.File;
import java.nio.file.Files;
import java.util.Map;

/**
 * Entry point — runs XFA fill test then flatten test.
 * Pass "fill" or "flatten" as arg to run only one scenario.
 */
public class Main {

    public static void main(String[] args) throws Exception {
        loadDotEnv();
        String mode = (args.length > 0 && !args[0].isBlank()) ? args[0].toLowerCase() : "all";

        System.out.println("=================================================");
        System.out.println("  APDFL XFA Form Test — IMM 1294");
        System.out.println("=================================================");


        boolean runFill    = mode.equals("all") || mode.equals("fill");
        boolean runFlatten = mode.equals("all") || mode.equals("flatten");
        boolean runBarcode = mode.equals("all") || mode.equals("barcode");
        boolean runAcrobat         = mode.equals("acrobat");
        boolean runAcrobatHeadless = mode.equals("acrobat-headless");
        boolean runValidate        = mode.equals("validate");
        boolean runDiscover        = mode.equals("discover");
        boolean runExport          = mode.equals("export");

        if (runFill) {
            System.out.println("\n[1/3] Running XfaFormFiller test...\n");
            try {
                XfaFormFiller.run();
            } catch (Exception e) {
                System.err.println("[FAIL] XfaFormFiller: " + e.getMessage());
                e.printStackTrace();
            }
        }

        if (runFlatten) {
            System.out.println("\n[2/3] Running FlattenTest...\n");
            try {
                FlattenTest.run();
            } catch (Exception e) {
                System.err.println("[FAIL] FlattenTest: " + e.getMessage());
                e.printStackTrace();
            }
        }

        if (runBarcode) {
            System.out.println("\n[3/3] Running BarcodeTest (datasets injection)...\n");
            try {
                BarcodeTest.run();
            } catch (Exception e) {
                System.err.println("[FAIL] BarcodeTest: " + e.getMessage());
                e.printStackTrace();
            }
        }

        if (runAcrobat) {
            System.out.println("\n[acrobat] Running AcrobatBarcodeStep...\n");
            try {
                AcrobatBarcodeStep.run();
            } catch (Exception e) {
                System.err.println("[FAIL] AcrobatBarcodeStep: " + e.getMessage());
                e.printStackTrace();
            }
        }

        if (runValidate) {
            System.out.println("\n[validate] Running AcrobatValidateStep...\n");
            try {
                AcrobatValidateStep.run();
            } catch (Exception e) {
                System.err.println("[FAIL] AcrobatValidateStep: " + e.getMessage());
                e.printStackTrace();
            }
        }

        if (runDiscover) {
            System.out.println("\n[discover] Running XfaDiscovery...\n");
            try {
                XfaDiscovery.run();
            } catch (Exception e) {
                System.err.println("[FAIL] XfaDiscovery: " + e.getMessage());
                e.printStackTrace();
            }
        }

        if (runExport) {
            System.out.println("\n[export] Running XfaExport...\n");
            try {
                XfaExport.run();
            } catch (Exception e) {
                System.err.println("[FAIL] XfaExport: " + e.getMessage());
                e.printStackTrace();
            }
        }

        if (runAcrobatHeadless) {
            System.out.println("\n[acrobat-headless] Running AcrobatHeadlessStep (no GUI)...\n");
            try {
                AcrobatHeadlessStep.run();
            } catch (Exception e) {
                System.err.println("[FAIL] AcrobatHeadlessStep: " + e.getMessage());
                e.printStackTrace();
            }
        }

        System.out.println("\n=================================================");
        System.out.println("  Done. Check output/ folder for result PDFs.");
        System.out.println("  Modes: fill | flatten | barcode | validate | discover | export | acrobat | acrobat-headless | all");
        System.out.println("=================================================");
    }

    /**
     * Loads a .env file from the project base directory (next to pom.xml).
     * Each non-blank, non-comment line must be KEY=VALUE.
     * Values are stored as system properties under the key "env.KEY" so that
     * XfaFormFiller.env() can pick them up without touching the OS env map.
     * Already-set OS environment variables are NOT overridden.
     */
    private static void loadDotEnv() {
        File envFile = new File(
                System.getProperty("project.basedir", new File("").getAbsolutePath()), ".env");
        if (!envFile.exists()) return;

        try {
            int loaded = 0;
            for (String line : Files.readAllLines(envFile.toPath())) {
                line = line.strip();
                if (line.isEmpty() || line.startsWith("#")) continue;
                int eq = line.indexOf('=');
                if (eq < 1) continue;
                String key   = line.substring(0, eq).strip();
                String value = line.substring(eq + 1).strip();
                // Strip optional surrounding quotes
                if (value.length() >= 2 &&
                    ((value.startsWith("\"") && value.endsWith("\"")) ||
                     (value.startsWith("'")  && value.endsWith("'")))) {
                    value = value.substring(1, value.length() - 1);
                }
                // OS env takes precedence; don't override already-set system props either
                if (System.getenv(key) == null && System.getProperty("env." + key) == null) {
                    System.setProperty("env." + key, value);
                    loaded++;
                }
            }
            if (loaded > 0) System.out.println("[.env] Loaded " + loaded + " variable(s) from " + envFile);
        } catch (Exception e) {
            System.err.println("[.env] Failed to load " + envFile + ": " + e.getMessage());
        }
    }
}
