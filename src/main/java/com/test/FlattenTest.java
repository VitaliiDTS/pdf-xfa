package com.test;

import com.datalogics.PDFL.*;

import java.io.File;
import java.io.InputStream;
import java.util.EnumSet;

/**
 * Test 2 — Fill XFA fields, trigger validate/calculate, then flatten.
 *
 * flattenXFAFormFieldsAsIfPrinted() fires the XFA "print" event before
 * flattening.  The print event chain is:
 *   prePrint → calculate (barcode fields recompute) → validate → layout → render
 * This is the correct way to trigger barcode generation in a dynamic XFA form.
 *
 * Output: output/flattened_result.pdf
 */
public class FlattenTest {

    private static String OUTPUT_PDF = XfaFormFiller.BASE_DIR + "/output/flattened_result.pdf";

    public static void run() throws Exception {
        // ── 0. License ────────────────────────────────────────────────────────
        String licenseKey = XfaFormFiller.env("APDFL_LICENSE_KEY", null);
        if (licenseKey != null && !licenseKey.isBlank()) {
            Library.setLicenseKey(licenseKey);
        }

        // ── 1. Library ────────────────────────────────────────────────────────
        String nativesDir = new File("target/natives").getAbsolutePath();
        Library lib = XfaFormFiller.initLibrary(nativesDir);
        lib.setAllowOpeningXFA(true);
        System.out.println("[INFO] FlattenTest ready.  APDFL: " + Library.getAPDFLVersion());

        try {
            File inputFile = new File(XfaFormFiller.INPUT_PDF);
            if (!inputFile.exists()) {
                System.err.println("[ERROR] Input PDF not found: " + inputFile.getAbsolutePath());
                return;
            }

            // ── 2. Open ───────────────────────────────────────────────────────
            Document doc = XfaFormFiller.openDocument(XfaFormFiller.INPUT_PDF);
            System.out.println("[OK]  Opened.  Forms type: " + doc.getFormsType()
                    + "  isDynXFA: " + doc.isDynamicXFA());

            // ── 3. Import test data ───────────────────────────────────────────
            File xmlFile = new File(XfaFormFiller.INPUT_XML);
            if (xmlFile.exists()) {
                boolean imported = doc.importXFAFormsData(xmlFile.getAbsolutePath());
                System.out.println(imported
                    ? "[OK]  importXFAFormsData() succeeded."
                    : "[WARN] importXFAFormsData() returned false.");
            }

            // ── 4. Flatten with print event (triggers validate + barcode generation) ──
            System.out.println("\n[INFO] Flattening as if printed (fires XFA calculate/validate)...");

            if (doc.isDynamicXFA() || doc.isStaticXFA()) {
                // flattenXFAFormFieldsAsIfPrinted fires the XFA print event:
                //   prePrint → calculate (barcode fields recompute) → validate → layout
                // This is the correct trigger for barcode generation before flattening.
                long flattened = doc.flattenXFAFormFieldsAsIfPrinted();
                System.out.println("[OK]  flattenXFAFormFieldsAsIfPrinted() — fields flattened: " + flattened);
            } else {
                // Pure AcroForm — calculate then flatten
                doc.flattenAcroFormFields();
                System.out.println("[OK]  flattenAcroFormFields() done.");
            }

            // ── 5. Save ───────────────────────────────────────────────────────
            new File("output").mkdirs();
            doc.save(EnumSet.of(SaveFlags.FULL), OUTPUT_PDF);
            long sizeAfter = new File(OUTPUT_PDF).length();
            System.out.printf("[OK]  Saved: %s  (%.1f KB)%n", OUTPUT_PDF, sizeAfter / 1024.0);

            // ── 6. Inspect page resources for rendered content ────────────────
            System.out.println("[INFO] Output forms type after flatten: " + doc.getFormsType());
            inspectPageResources(doc);

            doc.close();

        } catch (Exception e) {
            System.err.println("[ERROR] FlattenTest: " + e.getMessage());
            throw e;
        }
        // lib.delete() omitted — same XFA cleanup DEP issue as XfaFormFiller.
    }

    /**
     * Walk every page's /Resources /XObject dict and report all Image and Form
     * XObjects.  After flattenXFAFormFieldsAsIfPrinted(), rendered barcodes
     * (PDF417) appear as Image XObjects — their presence confirms that the XFA
     * engine actually executed the barcode calculate event.
     */
    static void inspectPageResources(Document doc) {
        int numPages = doc.getNumPages();
        System.out.println("[INFO] Inspecting XObjects on all " + numPages + " pages...");
        int totalImages = 0;
        int totalForms  = 0;
        for (int p = 0; p < numPages; p++) {
            Page page = doc.getPage(p);
            try {
                PDFDict pageDict = page.getPDFDict();
                PDFObject resObj = pageDict.get("Resources");
                if (!(resObj instanceof PDFDict)) { page.delete(); continue; }
                PDFObject xobjObj = ((PDFDict) resObj).get("XObject");
                if (!(xobjObj instanceof PDFDict)) { page.delete(); continue; }
                PDFDict xobjects = (PDFDict) xobjObj;
                java.util.List<PDFObject> keys = xobjects.getKeys();
                int imgCount  = 0;
                int formCount = 0;
                for (PDFObject keyObj : keys) {
                    String key = (keyObj instanceof PDFName) ? ((PDFName) keyObj).getValue()
                               : (keyObj instanceof PDFString) ? ((PDFString) keyObj).getValue()
                               : keyObj.toString();
                    PDFObject obj = xobjects.get(key);
                    if (!(obj instanceof PDFStream)) continue;
                    PDFDict dict = ((PDFStream) obj).getDict();
                    PDFObject subtypeObj = dict.get("Subtype");
                    String subtype = (subtypeObj instanceof PDFName)
                            ? ((PDFName) subtypeObj).getValue() : "?";
                    if ("Image".equals(subtype)) {
                        imgCount++;
                    } else if ("Form".equals(subtype)) {
                        formCount++;
                        // On page 5 (barcode page): peek into the Form XObject stream
                        // to see if it contains real drawing commands (re f w h lines)
                        // vs just an empty content stream.
                        if (p == 4) {
                            try (InputStream cs = ((PDFStream) obj).getFilteredStream()) {
                                byte[] raw = cs.readAllBytes();
                                String content = new String(raw, 0, Math.min(raw.length, 300));
                                boolean hasDrawing = raw.length > 20
                                        && (content.contains(" re\n") || content.contains(" re ")
                                            || content.contains(" f\n")  || content.contains(" F\n")
                                            || content.contains(" m\n")  || content.contains(" l\n"));
                                System.out.printf("    Form XObj %s: %d bytes, hasDrawing=%b  [%.80s]%n",
                                        key, raw.length, hasDrawing,
                                        content.replaceAll("[\r\n]", "·"));
                            } catch (Exception ex) {
                                System.out.println("    Form XObj " + key + ": read error " + ex.getMessage());
                            }
                        }
                    }
                }
                if (imgCount > 0 || formCount > 0) {
                    System.out.printf("  Page %d: %d Image XObject(s), %d Form XObject(s)%n",
                            p + 1, imgCount, formCount);
                }
                totalImages += imgCount;
                totalForms  += formCount;
            } catch (Exception e) {
                System.err.println("  Page " + (p+1) + " resource error: " + e.getMessage());
            } finally {
                page.delete();
            }
        }
        System.out.printf("[INFO] Total across all pages: %d Image, %d Form XObjects%n",
                totalImages, totalForms);
        if (totalImages == 0 && totalForms == 0) {
            System.out.println("       → No XObjects found. Barcodes were NOT rendered by the XFA engine.");
        } else {
            System.out.println("       → XObjects present. Barcodes may be rendered — open PDF to verify visually.");
        }
    }
}
