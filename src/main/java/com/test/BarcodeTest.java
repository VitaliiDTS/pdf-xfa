package com.test;

import com.datalogics.PDFL.*;

import java.io.File;
import java.util.EnumSet;

/**
 * Step 2 — Barcode datasets injection test.
 *
 * Strategy: APDFL does not execute XFA JavaScript, so BC.encodeAll() never runs.
 * However, the form's Page5 has 5 text fields (TextField1[0..4]) whose rawValue
 * the JS would fill with pipe-delimited barcode strings.  We pre-compute those
 * strings with BarcodeEncoder and inject them directly via importXFAFormsData().
 *
 * If the XFA barcode widget is bound to those data nodes (PDF417 field type with
 * a data binding pointing to Page5.TextField1), the XFA layout/render engine that
 * fires during flattenXFAFormFieldsAsIfPrinted() may render the barcode natively.
 *
 * Output: output/barcode_inject_result.pdf
 * Verdict: inspectPageResources() reports Image XObjects (success) or empty (fail).
 */
public class BarcodeTest {

    private static final String BARCODE_XML  = XfaFormFiller.BASE_DIR + "/output/barcode_inject.xml";
    private static final String OUTPUT_PDF   = XfaFormFiller.BASE_DIR + "/output/barcode_inject_result.pdf";

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
        System.out.println("[INFO] BarcodeTest ready.  APDFL: " + Library.getAPDFLVersion());

        try {
            File inputFile = new File(XfaFormFiller.INPUT_PDF);
            if (!inputFile.exists()) {
                System.err.println("[ERROR] Input PDF not found: " + inputFile.getAbsolutePath());
                return;
            }

            // ── 2. Generate barcode strings ───────────────────────────────────
            FormData formData = FormData.testData();
            String[] barcodes = BarcodeEncoder.encode(formData);
            System.out.println("[INFO] Generated barcode strings:");
            for (int i = 0; i < barcodes.length; i++) {
                // Print first 120 chars to avoid console spam
                String preview = barcodes[i].length() > 120
                        ? barcodes[i].substring(0, 120) + "..." : barcodes[i];
                System.out.printf("  BC%d (%d chars): %s%n", i + 1, barcodes[i].length(), preview);
            }

            // ── 3. Open document ─────────────────────────────────────────────
            Document doc = XfaFormFiller.openDocument(XfaFormFiller.INPUT_PDF);
            System.out.println("[OK]  Opened.  Forms: " + doc.getFormsType()
                    + "  isDynXFA: " + doc.isDynamicXFA());

            // ── 5. Build combined XML: test_data + Page5 barcodes, single import ─
            // importXFAFormsData() REPLACES datasets on each call (not merges).
            // We must inject the Page5 barcode values into the main XML before
            // the single import call.
            File xmlFile = new File(XfaFormFiller.INPUT_XML);
            String combinedXml = BARCODE_XML.replace("barcode_inject.xml", "combined_inject.xml");
            buildCombinedXml(xmlFile.getAbsolutePath(), combinedXml, barcodes);
            System.out.println("[OK]  Written combined XML: " + combinedXml);

            boolean bcOk = doc.importXFAFormsData(combinedXml);
            System.out.println(bcOk
                    ? "[OK]  Combined data imported."
                    : "[WARN] Combined data import returned false.");

            // Export to verify the values were actually written
            String verifyXml = XfaFormFiller.BASE_DIR + "/output/barcode_inject_verify.xml";
            boolean exported = doc.exportXFAFormsData(verifyXml, XFAFormExportType.XML);
            if (exported) {
                System.out.println("[OK]  Post-import dump: " + verifyXml);
                checkBarcodeValuesInDump(verifyXml, barcodes);
            }

            // ── 7. Flatten with print event ───────────────────────────────────
            System.out.println("\n[INFO] Flattening as if printed...");
            long flattened = doc.flattenXFAFormFieldsAsIfPrinted();
            System.out.println("[OK]  Fields flattened: " + flattened);

            // ── 8. Save ───────────────────────────────────────────────────────
            doc.save(EnumSet.of(SaveFlags.FULL), OUTPUT_PDF);
            long size = new File(OUTPUT_PDF).length();
            System.out.printf("[OK]  Saved: %s  (%.1f KB)%n", OUTPUT_PDF, size / 1024.0);

            // ── 9. Inspect for rendered barcodes ─────────────────────────────
            System.out.println("[INFO] Forms type after flatten: " + doc.getFormsType());
            FlattenTest.inspectPageResources(doc);

            doc.close();

        } catch (Exception e) {
            System.err.println("[ERROR] BarcodeTest: " + e.getMessage());
            throw e;
        }
        // lib.delete() omitted — XFA cleanup DEP issue
    }

    /**
     * Reads the base test_data.xml and inserts a <Page5> block with barcode
     * values before the closing </form1> tag, producing one combined XML.
     * This avoids the double-import problem (second call replaces datasets).
     */
    private static void buildCombinedXml(String basePath, String outPath, String[] barcodes) throws Exception {
        String base = java.nio.file.Files.readString(java.nio.file.Paths.get(basePath));

        StringBuilder page5 = new StringBuilder();
        page5.append("\n<Page5>\n");
        for (String bc : barcodes) {
            page5.append("  <TextField1>").append(escapeXml(bc)).append("</TextField1>\n");
        }
        page5.append("</Page5>\n");

        // Insert before </form1>
        int insertAt = base.lastIndexOf("</form1>");
        String combined;
        if (insertAt >= 0) {
            combined = base.substring(0, insertAt) + page5 + base.substring(insertAt);
        } else {
            // Fallback: append before closing datasets tag
            combined = base.replace("</xfa:data>", page5 + "</xfa:data>");
        }
        java.nio.file.Files.writeString(java.nio.file.Paths.get(outPath), combined);
    }

    /** Minimal XML character escaping for element content. */
    private static String escapeXml(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");
    }

    /**
     * Scans the post-import XFA dump XML for the barcode string values.
     * Confirms whether importXFAFormsData() actually wrote them.
     */
    private static void checkBarcodeValuesInDump(String dumpPath, String[] barcodes) {
        try {
            String content = java.nio.file.Files.readString(java.nio.file.Paths.get(dumpPath));
            System.out.println("[INFO] Checking dump for barcode values:");
            for (int i = 0; i < barcodes.length; i++) {
                // Check header token which is unique
                String header = "IMM1294_06-2018_" + (i + 1) + "|";
                boolean found = content.contains(header);
                System.out.printf("  BC%d header '%s' in dump: %s%n", i + 1, header, found ? "YES ✓" : "NO ✗");
            }
        } catch (Exception e) {
            System.err.println("[WARN] checkBarcodeValuesInDump: " + e.getMessage());
        }
    }
}
