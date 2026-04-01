package com.test;

import com.datalogics.PDFL.*;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

/**
 * Discovers XFA field structure of a form and writes it to the form folder.
 *
 * Run with:
 *   mvn compile exec:exec "-Dexec.mode=discover" "-Dform.dir=forms/imm1294"
 *
 * Outputs (inside <form.dir>/):
 *   xfa_fields.xml   — current XFA data export (shows all field paths/values)
 *   xfa_template.xml — XFA template packet (field definitions, types, bindings)
 *   xfa_form.xml     — XFA form packet if present
 */
public class XfaDiscovery {

    public static void run() throws Exception {
        String formDir = System.getProperty("form.dir");
        if (formDir == null || formDir.isBlank()) {
            System.err.println("[ERROR] -Dform.dir=<path> is required for discover mode.");
            System.err.println("        Example: mvn compile exec:exec \"-Dexec.mode=discover\" \"-Dform.dir=forms/imm1294\"");
            return;
        }

        String baseDir   = XfaFormFiller.BASE_DIR;
        String formPath  = baseDir + "/" + formDir;
        String inputPdf  = formPath + "/template.pdf";
        String outputDir = formPath;   // write discovery files directly into the form folder

        System.out.println("[discover] Form dir : " + formPath);
        System.out.println("[discover] Input PDF: " + inputPdf);

        File pdfFile = new File(inputPdf);
        if (!pdfFile.exists()) {
            System.err.println("[ERROR] template.pdf not found: " + pdfFile.getAbsolutePath());
            System.err.println("        Copy the PDF into the form folder and rename it template.pdf");
            return;
        }

        String licenseKey = XfaFormFiller.env("APDFL_LICENSE_KEY", null);
        if (licenseKey != null && !licenseKey.isBlank()) {
            Library.setLicenseKey(licenseKey);
        }

        String nativesDir = new File(baseDir, "target/natives").getAbsolutePath();
        Library lib = XfaFormFiller.initLibrary(nativesDir);
        lib.setAllowOpeningXFA(true);
        System.out.println("[discover] APDFL " + Library.getAPDFLVersion());

        try {
            Document doc = XfaFormFiller.openDocument(inputPdf);
            System.out.println("[discover] Pages     : " + doc.getNumPages());
            System.out.println("[discover] Forms type: " + doc.getFormsType());
            System.out.println("[discover] Dynamic   : " + doc.isDynamicXFA());

            // 1. Export current XFA data → xfa_fields.xml (correct structure, empty values)
            String fieldsXml = outputDir + "/xfa_fields.xml";
            boolean ok = doc.exportXFAFormsData(fieldsXml, XFAFormExportType.XML);
            if (ok) {
                System.out.println("[discover] Exported field data → " + fieldsXml);

                // Auto-create data.xml from the exported structure if it doesn't exist yet
                File dataXml = new File(outputDir + "/data.xml");
                if (!dataXml.exists()) {
                    Files.copy(Paths.get(fieldsXml), dataXml.toPath());
                    System.out.println("[discover] Created data.xml (copy of xfa_fields.xml — fill in the values)");
                } else {
                    System.out.println("[discover] data.xml already exists — not overwritten");
                }

                printXmlPreview(fieldsXml, 40);
            } else {
                System.out.println("[WARN] exportXFAFormsData returned false — trying raw stream dump");
            }

            // 2. Extract XFA template / form / datasets packets from PDF structure
            extractXfaPackets(doc, outputDir);

            doc.close();
            System.out.println("\n[discover] Done. Check the form folder for:");
            System.out.println("  data.xml         — edit this with real applicant values");
            System.out.println("  xfa_fields.xml   — original empty field structure (reference)");
            System.out.println("  xfa_template.xml — full field definitions");
            System.out.println("\n  Next steps:");
            System.out.println("  1. Edit " + formPath + "/data.xml  with real values");
            System.out.println("  2. Screenshot the Validate button in Acrobat, save as " + formPath + "/button.png");
            System.out.println("  3. mvn compile exec:exec \"-Dexec.mode=validate\" \"-Dform.dir=" + formDir + "\"");
        } catch (Exception e) {
            System.err.println("[ERROR] XfaDiscovery: " + e.getMessage());
            throw e;
        }
    }

    private static void extractXfaPackets(Document doc, String outputDir) {
        System.out.println("\n[discover] Extracting XFA packets...");
        try {
            PDFDict root = doc.getRoot();
            PDFObject acroFormObj = root.get("AcroForm");
            if (!(acroFormObj instanceof PDFDict)) {
                System.out.println("  No AcroForm dict.");
                return;
            }
            PDFObject xfaObj = ((PDFDict) acroFormObj).get("XFA");
            if (!(xfaObj instanceof PDFArray)) {
                System.out.println("  No XFA array.");
                return;
            }

            PDFArray arr = (PDFArray) xfaObj;
            System.out.println("  XFA array: " + arr.getLength() + " items");

            for (int i = 0; i + 1 < arr.getLength(); i += 2) {
                PDFObject nameObj   = arr.get(i);
                PDFObject streamObj = arr.get(i + 1);
                if (!(streamObj instanceof PDFStream)) continue;

                String packetName = nameObj instanceof PDFString ? ((PDFString) nameObj).getValue()
                                  : nameObj instanceof PDFName   ? ((PDFName)   nameObj).getValue()
                                  : "packet_" + i;
                // Skip wrapper packets (xdp:xdp envelope) — not useful data
                if (packetName.contains(":") || packetName.contains("<") || packetName.contains(">")) {
                    System.out.println("  skip: " + packetName);
                    continue;
                }

                PDFStream ps = (PDFStream) streamObj;
                try (InputStream is = ps.getFilteredStream()) {
                    byte[] data = is.readAllBytes();
                    String outFile = outputDir + "/xfa_" + packetName + ".xml";
                    Files.write(Paths.get(outFile), data);
                    System.out.printf("  %-20s %6d bytes → %s%n",
                            packetName, data.length, outFile);
                } catch (Exception ex) {
                    System.out.println("  " + packetName + ": read error — " + ex.getMessage());
                }
            }
        } catch (Exception e) {
            System.err.println("[ERROR] extractXfaPackets: " + e.getMessage());
        }
    }

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
            System.err.println("[WARN] preview: " + e.getMessage());
        }
    }
}
