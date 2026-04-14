package com.test;

import com.datalogics.PDFL.*;

import java.io.File;

/**
 * Export mode — reads an existing filled/validated XFA PDF and dumps its data to XML.
 *
 * Input:  forms/<form.dir>/export_input.pdf
 * Output: forms/<form.dir>/export_output.xml
 *
 * Usage:
 *   mvn exec:exec "-Dexec.mode=export" "-Dform.dir=forms/imm1294"
 */
public class XfaExport {

    public static void run() throws Exception {
        String formDir = System.getProperty("form.dir");
        if (formDir == null || formDir.isBlank()) {
            System.err.println("[ERROR] -Dform.dir=<path> is required for export mode.");
            return;
        }

        String inputPdf  = XfaFormFiller.BASE_DIR + "/" + formDir + "/export_input.pdf";
        String outputXml = XfaFormFiller.BASE_DIR + "/" + formDir + "/export_output.xml";

        File inputFile = new File(inputPdf);
        if (!inputFile.exists()) {
            System.err.println("[ERROR] Input PDF not found: " + inputFile.getAbsolutePath());
            System.err.println("        Place your PDF at: " + inputFile.getAbsolutePath());
            return;
        }

        System.out.println("[export] Input  : " + inputFile.getAbsolutePath());
        System.out.println("[export] Output : " + outputXml);

        String licenseKey = XfaFormFiller.env("APDFL_LICENSE_KEY", null);
        if (licenseKey != null && !licenseKey.isBlank()) {
            Library.setLicenseKey(licenseKey);
        }

        String nativesDir = new File(System.getProperty("project.basedir",
                new File("").getAbsolutePath()), "target/natives").getAbsolutePath();
        Library lib = XfaFormFiller.initLibrary(nativesDir);
        lib.setAllowOpeningXFA(true);

        try {
            Document doc = XfaFormFiller.openDocument(inputPdf);

            boolean ok = doc.exportXFAFormsData(outputXml, XFAFormExportType.XML);
            doc.close();

            if (ok && new File(outputXml).exists()) {
                System.out.printf("[OK] Exported: %s  (%.1f KB)%n",
                        outputXml, new File(outputXml).length() / 1024.0);
            } else {
                System.err.println("[WARN] exportXFAFormsData returned false or file not created.");
            }
        } catch (Exception e) {
            System.err.println("[ERROR] XfaExport: " + e.getMessage());
            throw e;
        }
    }
}
