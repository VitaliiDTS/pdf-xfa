package com.test;

import com.datalogics.PDFL.*;

import java.io.*;
import java.util.EnumSet;
import java.util.List;

/**
 * Test 1 — Fill XFA form fields and save.
 *
 * Real APDFL 18.59.0 API (verified from JAR):
 *   - Document(String path, String password, PermissionRequestOperation, boolean)
 *   - Library.setAllowOpeningXFA(true)  -- required for dynamic XFA
 *   - doc.isDynamicXFA() / isStaticXFA() / getFormsType()
 *   - doc.importXFAFormsData(String filePath)  -- takes file path, returns boolean
 *   - doc.exportXFAFormsData(String filePath, XFAFormExportType)
 *   - doc.flattenXFAFormFields()  -- returns long (count of flattened fields)
 *   - PDFStream.getFilteredStream() returns InputStream (not byte[])
 *   - Page.delete() instead of close()
 */
public class XfaFormFiller {

    // Paths relative to project basedir (passed via system property, fallback to ../../../)
    static String BASE_DIR = System.getProperty("project.basedir",
            new File("").getAbsolutePath().contains("natives")
            ? new File("../../..").getAbsolutePath()
            : new File("").getAbsolutePath());

    // Optional: -Dform.dir=forms/imm1294  selects a form folder under BASE_DIR.
    // Each form folder contains: template.pdf, data.xml, button.png, output/
    static String FORM_DIR = blankToNull(System.getProperty("form.dir", null));

    // Env-configurable paths (override via environment variables):
    //   APDFL_INPUT_PDF  — full path to input PDF
    //   APDFL_INPUT_XML  — full path to input XML data file
    static String INPUT_PDF = FORM_DIR != null
            ? BASE_DIR + "/" + FORM_DIR + "/template.pdf"
            : env("APDFL_INPUT_PDF", BASE_DIR + "/input/IMM1294 - 2023.11 - CURRENT.pdf");
    static String INPUT_XML = FORM_DIR != null
            ? BASE_DIR + "/" + FORM_DIR + "/data.xml"
            : env("APDFL_INPUT_XML", BASE_DIR + "/src/main/resources/test_data.xml");
    static String OUTPUT_DIR = FORM_DIR != null
            ? BASE_DIR + "/" + FORM_DIR + "/output"
            : BASE_DIR + "/output";
    static String OUTPUT_PDF         = OUTPUT_DIR + "/filled_result.pdf";
    static String OUTPUT_PDF_PRINTED = OUTPUT_DIR + "/printed_result.pdf";
    static String DUMP_XML           = OUTPUT_DIR + "/current_xfa_dump.xml";

    /**
     * Returns the value for the given variable name, checking in order:
     *   1. OS environment variable (set before JVM launch)
     *   2. System property "env.NAME" (set by Main.loadDotEnv() from .env file)
     *   3. fallback
     */
    static String blankToNull(String s) { return (s == null || s.isBlank()) ? null : s; }

    static String env(String name, String fallback) {
        String val = System.getenv(name);
        if (val != null && !val.isBlank()) return val;
        val = System.getProperty("env." + name);
        return (val != null && !val.isBlank()) ? val : fallback;
    }

    public static void run() throws Exception {
        // ── 0. License ────────────────────────────────────────────────────────
        String licenseKey = env("APDFL_LICENSE_KEY", null);
        if (licenseKey != null && !licenseKey.isBlank()) {
            System.out.println("[INFO] Applying license key...");
            Library.setLicenseKey(licenseKey);
        } else {
            System.out.println("[WARN] APDFL_LICENSE_KEY not set — running in demo mode.");
        }

        // ── 1. Library init with plugin directory (Forms Extension .ppi files) ──
        // Use project.basedir system property (set by pom.xml) for reliable path resolution
        String projectBase = System.getProperty("project.basedir",
                new File("").getAbsolutePath());
        String nativesDir = new File(projectBase, "target/natives").getAbsolutePath();
        System.out.println("[INFO] Project base: " + projectBase);
        System.out.println("[INFO] Natives dir:  " + nativesDir);

        Library lib = initLibrary(nativesDir);
        lib.setAllowOpeningXFA(true);
        System.out.println("[OK]  Library ready.");
        System.out.println("      APDFL version : " + Library.getAPDFLVersion());
        System.out.println("      DLE   version : " + Library.getDLEVersion());
        System.out.println("      Install dir   : " + Library.getInstallLocation());
        System.out.println("      Resource dir  : " + Library.getResourceDirectory());
        System.out.println("      XFA allowed   : " + lib.getAllowOpeningXFA());

        try {
            // ── 2. Check input ────────────────────────────────────────────────
            File inputFile = new File(INPUT_PDF);
            if (!inputFile.exists()) {
                System.err.println("[ERROR] Input PDF not found: " + inputFile.getAbsolutePath());
                System.err.println("        Copy IMM1294 PDF to the input/ folder and retry.");
                return;
            }
            long sizeBefore = inputFile.length();
            System.out.printf("[INFO] Input: %s (%.1f KB)%n",
                    inputFile.getAbsolutePath(), sizeBefore / 1024.0);

            // ── 3. Open encrypted XFA document ───────────────────────────────
            Document doc = openDocument(INPUT_PDF);
            System.out.println("[OK]  Document opened.");
            System.out.println("      Pages      : " + doc.getNumPages());
            System.out.println("      Forms type : " + doc.getFormsType());
            System.out.println("      Dynamic XFA: " + doc.isDynamicXFA());
            System.out.println("      Static  XFA: " + doc.isStaticXFA());

            // ── 4a. Dump XFA template to find barcode field bindings ─────────
            dumpXfaTemplate(doc);

            // ── 4b. Export current XFA data so we can inspect field names ────
            new File(OUTPUT_DIR).mkdirs();
            System.out.println("\n[INFO] Exporting current XFA data to " + DUMP_XML + " ...");
            boolean exported = doc.exportXFAFormsData(DUMP_XML, XFAFormExportType.XML);
            if (exported) {
                System.out.println("[OK]  XFA data exported. Open output/current_xfa_dump.xml");
                System.out.println("      to find the real XFA element names, then update test_data.xml.");
                printXmlPreview(DUMP_XML, 60);
            } else {
                System.out.println("[WARN] exportXFAFormsData() returned false.");
                // Fallback: dump raw XFA streams from PDF structure
                dumpXfaStreams(doc);
            }

            // ── 5. Import test data ───────────────────────────────────────────
            File xmlFile = new File(INPUT_XML);
            if (xmlFile.exists()) {
                System.out.println("\n[INFO] Importing XFA data from " + xmlFile.getAbsolutePath());
                // importXFAFormsData takes a file path
                boolean imported = doc.importXFAFormsData(xmlFile.getAbsolutePath());
                System.out.println(imported
                    ? "[OK]  importXFAFormsData() succeeded."
                    : "[WARN] importXFAFormsData() returned false — data may not have been applied.");
            } else {
                System.err.println("[WARN] test_data.xml not found: " + xmlFile.getAbsolutePath());
            }

            // ── 6. Inspect filled doc before saving (export XFA data to verify) ─
            System.out.println("\n[INFO] Inspecting filled document (pre-save)...");
            inspectOutput(doc, OUTPUT_PDF);

            // ── 7. Save filled document (XFA form with data, not yet flattened) ─
            System.out.println("\n[INFO] Saving filled (XFA) to " + OUTPUT_PDF + " ...");
            doc.save(EnumSet.of(SaveFlags.FULL), OUTPUT_PDF);
            long sizeAfter = new File(OUTPUT_PDF).length();
            System.out.printf("[OK]  Saved. Before: %.1f KB  After: %.1f KB%n",
                    sizeBefore / 1024.0, sizeAfter / 1024.0);
            doc.close();

            // ── 8. Re-open and flatten as if printed (fires validate + barcodes) ─
            // flattenXFAFormFieldsAsIfPrinted() fires the XFA "print" event:
            //   prePrint → calculate (barcodes recompute) → validate → layout
            System.out.println("\n[INFO] Re-opening to run print-event flatten...");
            Document doc2 = openDocument(OUTPUT_PDF);
            long flattened = doc2.flattenXFAFormFieldsAsIfPrinted();
            System.out.println("[OK]  flattenXFAFormFieldsAsIfPrinted() — fields: " + flattened);
            doc2.save(EnumSet.of(SaveFlags.FULL), OUTPUT_PDF_PRINTED);
            long sizePrinted = new File(OUTPUT_PDF_PRINTED).length();
            System.out.printf("[OK]  Printed result: %s  (%.1f KB)%n",
                    OUTPUT_PDF_PRINTED, sizePrinted / 1024.0);
            System.out.println("[INFO] Forms type after print-flatten: " + doc2.getFormsType());

            // ── 9. Inspect Form XObjects on printed result ────────────────────
            FlattenTest.inspectPageResources(doc2);
            doc2.close();

        } catch (Exception e) {
            System.err.println("[ERROR] XfaFormFiller: " + e.getMessage());
            throw e;
        }
        // Note: lib.delete() intentionally omitted — APDFL's XFA engine cleanup
        // triggers a DEP violation (DL180pdfl.dll+0x5df74a) on JVM exit. The Library
        // is a process-wide singleton; resources are reclaimed when the JVM terminates.
    }

    // ──────────────────────────────────────────────────────────────────────────

    /**
     * Try multiple Library init strategies to load Forms Extension plugins.
     *
     * The .ppi plugin files (DL180Acroform.ppi, DL180EScript.ppi, etc.)
     * from forms-extension-win-x86-64-jni.zip must be discoverable by APDFL.
     *
     * Library constructors available:
     *   Library()
     *   Library(List<String> searchPaths)
     *   Library(List<String>, String installLoc, String resourceDir, EnumSet<LibraryFlags>)
     *   Library(List<String>, String installLoc, String resourceDir, String pluginDir, EnumSet<LibraryFlags>)
     */
    static Library initLibrary(String nativesDir) {
        // Pre-load Forms Extension DLLs so they are already in the process module list.
        // APDFL may detect loaded modules and register them as plugins.
        preloadFormsExtension(nativesDir);

        EnumSet<LibraryFlags> feFlags = EnumSet.of(LibraryFlags.INIT_FORMS_EXTENSION);

        // Strategy A: INIT_FORMS_EXTENSION + installLocation (4-arg)
        try {
            System.out.println("[INFO] Library init A: INIT_FORMS_EXTENSION + installLoc=" + nativesDir);
            return new Library(List.of(nativesDir), nativesDir, nativesDir, feFlags);
        } catch (Exception e) {
            System.err.println("[WARN] Strategy A failed: " + e.getMessage());
        }

        // Strategy B: INIT_FORMS_EXTENSION + pluginDir (5-arg)
        try {
            System.out.println("[INFO] Library init B: 5-arg, pluginDir=" + nativesDir);
            return new Library(List.of(nativesDir), nativesDir, nativesDir, nativesDir, feFlags);
        } catch (Exception e) {
            System.err.println("[WARN] Strategy B failed: " + e.getMessage());
        }

        // Strategy C: INIT_FORMS_EXTENSION only, default paths
        try {
            System.out.println("[INFO] Library init C: INIT_FORMS_EXTENSION, default paths");
            return new Library(feFlags);
        } catch (Exception e) {
            System.err.println("[WARN] Strategy C failed: " + e.getMessage());
        }

        // Strategy D: default (no FE)
        System.out.println("[INFO] Library init D: default constructor");
        return new Library();
    }

    /**
     * Force-load the Forms Extension native DLLs before APDFL Library init.
     * .ppi files on Windows are renamed DLLs. Loading them ensures APDFL can
     * register them as loaded modules.
     */
    private static void preloadFormsExtension(String nativesDir) {

        // Force-load the core Forms Extension DLLs
        String[] toLoad = {
            "DL180AXSLE.dll",       // XFA Scripting Language Engine
            "DL180Acroform.ppi",    // AcroForms / Forms Extension plugin
            "DL180EScript.ppi",     // EcmaScript engine
            "DL180PDFLibPI.ppi",    // PDF Library plugin interface
        };
        for (String dll : toLoad) {
            File f = new File(nativesDir, dll);
            if (f.exists()) {
                try {
                    System.load(f.getAbsolutePath());
                    System.out.println("[INFO] Preloaded: " + dll);
                } catch (UnsatisfiedLinkError e) {
                    System.err.println("[WARN] Could not preload " + dll + ": " + e.getMessage());
                }
            }
        }
    }

    static Document openDocument(String path) {
        // Strategy 1: empty password + ALL_OPERATIONS permission
        try {
            System.out.println("[INFO] Opening with empty password + ALL_OPERATIONS...");
            return new Document(path, "", PermissionRequestOperation.ALL_OPERATIONS, false);
        } catch (Exception e) {
            System.err.println("[WARN] Failed: " + e.getMessage());
        }
        // Strategy 2: open without explicit password
        try {
            System.out.println("[INFO] Opening without explicit password...");
            return new Document(path);
        } catch (Exception e) {
            System.err.println("[WARN] Failed: " + e.getMessage());
            throw new RuntimeException("Cannot open document: " + path, e);
        }
    }

    /** Print first N lines of an XML file to console for quick field-name inspection. */
    private static void printXmlPreview(String path, int maxLines) {
        try (BufferedReader r = new BufferedReader(new FileReader(path))) {
            System.out.println("  --- XML preview (first " + maxLines + " lines) ---");
            String line;
            int count = 0;
            while ((line = r.readLine()) != null && count++ < maxLines) {
                System.out.println("  " + line);
            }
            if (count >= maxLines) System.out.println("  ... (truncated)");
        } catch (Exception e) {
            System.err.println("[WARN] Cannot read preview: " + e.getMessage());
        }
    }

    /** Fallback: dump raw XFA streams from PDF internal structure. */
    private static void dumpXfaStreams(Document doc) {
        System.out.println("[INFO] Attempting raw XFA stream dump...");
        try {
            PDFDict root = doc.getRoot();
            PDFObject acroFormObj = root.get("AcroForm");
            if (!(acroFormObj instanceof PDFDict)) {
                System.out.println("  No AcroForm dict found.");
                return;
            }
            PDFDict acroForm = (PDFDict) acroFormObj;
            PDFObject xfaObj = acroForm.get("XFA");
            if (xfaObj == null) {
                System.out.println("  No XFA entry in AcroForm.");
                return;
            }
            System.out.println("  XFA type: " + xfaObj.getClass().getSimpleName());

            if (xfaObj instanceof PDFArray) {
                PDFArray arr = (PDFArray) xfaObj;
                System.out.println("  XFA array length: " + arr.getLength());
                for (int i = 0; i < arr.getLength(); i++) {
                    PDFObject item = arr.get(i);
                    if (item instanceof PDFName) {
                        System.out.println("  XFA[" + i + "] = \"" + ((PDFName) item).getValue() + "\"");
                    } else if (item instanceof PDFStream) {
                        PDFStream stream = (PDFStream) item;
                        // getFilteredStream() returns InputStream
                        try (InputStream is = stream.getFilteredStream()) {
                            byte[] data = is.readAllBytes();
                            String text = new String(data, 0, Math.min(data.length, 600));
                            System.out.println("  XFA[" + i + "] stream (" + data.length + " bytes):");
                            System.out.println("    " + text.substring(0, Math.min(text.length(), 400))
                                    .replaceAll("[\r\n]+", " "));
                        }
                    }
                }
            } else if (xfaObj instanceof PDFStream) {
                try (InputStream is = ((PDFStream) xfaObj).getFilteredStream()) {
                    byte[] data = is.readAllBytes();
                    System.out.println("  XFA single stream (" + data.length + " bytes):");
                    System.out.println(new String(data, 0, Math.min(data.length, 800)));
                }
            }
        } catch (Exception e) {
            System.err.println("[ERROR] dumpXfaStreams: " + e.getMessage());
        }
    }

    /**
     * Find the XFA "template" stream in the PDF and search it for barcode-
     * related field names.  The template defines field names, data bindings,
     * and types (PDF417, DataMatrix, etc.) — exactly what we need to know
     * which data-model paths to write the encoded barcode strings into.
     */
    static void dumpXfaTemplate(Document doc) {
        System.out.println("[INFO] Searching XFA template for barcode field names...");
        try {
            PDFDict root = doc.getRoot();
            PDFObject acroFormObj = root.get("AcroForm");
            if (!(acroFormObj instanceof PDFDict)) { System.out.println("  No AcroForm."); return; }
            PDFObject xfaObj = ((PDFDict) acroFormObj).get("XFA");
            if (!(xfaObj instanceof PDFArray)) { System.out.println("  No XFA array."); return; }

            PDFArray arr = (PDFArray) xfaObj;
            System.out.println("  XFA array length: " + arr.getLength());

            // Print all packet names and their declared/actual sizes
            for (int i = 0; i < arr.getLength(); i++) {
                PDFObject item = arr.get(i);
                if (item instanceof PDFString) {
                    System.out.println("  XFA[" + i + "] name = \"" + ((PDFString) item).getValue() + "\"");
                } else if (item instanceof PDFName) {
                    System.out.println("  XFA[" + i + "] name = \"" + ((PDFName) item).getValue() + "\"");
                } else if (item instanceof PDFStream) {
                    PDFStream ps = (PDFStream) item;
                    int declaredLen = ps.getLength();
                    try (InputStream is2 = ps.getFilteredStream()) {
                        byte[] b = is2.readAllBytes();
                        System.out.println("  XFA[" + i + "] stream: declared=" + declaredLen
                                + " filtered=" + b.length + " bytes");
                    } catch (Exception ex) {
                        System.out.println("  XFA[" + i + "] stream: declared=" + declaredLen
                                + " read-error=" + ex.getMessage());
                    }
                } else {
                    System.out.println("  XFA[" + i + "] " + item.getClass().getSimpleName());
                }
            }

            // XFA packets alternate: PDFString/PDFName (packet-name), PDFStream (content)
            for (int i = 0; i + 1 < arr.getLength(); i += 2) {
                PDFObject nameObj = arr.get(i);
                PDFObject streamObj = arr.get(i + 1);
                if (!(streamObj instanceof PDFStream)) continue;
                String packetName = (nameObj instanceof PDFString) ? ((PDFString) nameObj).getValue()
                                  : (nameObj instanceof PDFName)   ? ((PDFName)   nameObj).getValue()
                                  : null;
                // Search both "template" and "form" packets for barcode field definitions
                if (!"template".equals(packetName) && !"form".equals(packetName)) continue;

                PDFStream ps = (PDFStream) streamObj;
                System.out.printf("  Found '%s' packet. declared=%d bytes%n",
                        packetName, ps.getLength());
                try (InputStream is = ps.getUnfilteredStream()) {
                    byte[] rawBytes = is.readAllBytes();
                    System.out.println("  Unfiltered size: " + rawBytes.length + " bytes");
                }
                try (InputStream is = ps.getFilteredStream()) {
                    String tmpl = new String(is.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
                    System.out.printf("  Filtered size: %d chars%n", tmpl.length());

                    // Print every line that mentions barcode / PDF417 / field name
                    String[] lines = tmpl.split("\n");
                    System.out.println("  Lines matching barcode/PDF417/field:");
                    int printed = 0;
                    for (String line : lines) {
                        String lo = line.toLowerCase();
                        if (lo.contains("barcode") || lo.contains("pdf417") || lo.contains("datamatrix")
                                || lo.contains("qrcode") || lo.contains("paperforms")) {
                            System.out.println("    " + line.strip());
                            if (++printed >= 80) { System.out.println("    ... (truncated at 80 matches)"); break; }
                        }
                    }
                    if (printed == 0) System.out.println("    (none found — barcode rendering may be via XFA script only)");

                    // Save the packet for offline inspection
                    String tmplPath = OUTPUT_DIR + "/xfa_" + packetName + ".xml";
                    java.nio.file.Files.writeString(java.nio.file.Paths.get(tmplPath), tmpl);
                    System.out.println("  Saved → " + tmplPath);
                }
            }
        } catch (Exception e) {
            System.err.println("[ERROR] dumpXfaTemplate: " + e.getMessage());
        }
    }

    /** Inspect output document using the already-open doc (no second Library). */
    static void inspectOutput(Document doc, String savedPath) {
        try {
            System.out.println("  Pages in output: " + doc.getNumPages());
            System.out.println("  Forms type:      " + doc.getFormsType());
            System.out.println("  Dynamic XFA:     " + doc.isDynamicXFA());

            // Export XFA data from the saved file path name (just for the xml filename)
            String filledXml = savedPath.replace(".pdf", "_xfa_data.xml");
            boolean ok = doc.exportXFAFormsData(filledXml, XFAFormExportType.XML);
            if (ok) {
                System.out.println("  XFA data exported to: " + filledXml);
                System.out.println("  Check that file to verify field values were written.");
            }
        } catch (Exception e) {
            System.err.println("[WARN] inspectOutput: " + e.getMessage());
        }
    }
}
