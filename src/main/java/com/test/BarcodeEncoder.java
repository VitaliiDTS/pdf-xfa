package com.test;

public class BarcodeEncoder {

    // ── Helpers ──────────────────────────────────────────────────────────────

    /** Null-safe value: returns s if non-null, otherwise "". */
    private static String nvl(String s) {
        return s != null ? s : "";
    }

    /** Appends (nvl(val) + "|") to sb. */
    private static void append(StringBuilder sb, String val) {
        sb.append(nvl(val)).append('|');
    }

    /**
     * Returns the formatted phone / fax number string.
     * Canada/US format : "(areaCode) firstThree-lastFive"
     * International    : "+numberCountry intlNumber"
     * Neither          : ""
     */
    private static String phoneActualNumber(
            String canadaUS, String other,
            String areaCode, String firstThree, String lastFive,
            String numberCountry, String intlNumber) {

        if ("1".equals(canadaUS)) {
            return "(" + nvl(areaCode) + ") " + nvl(firstThree) + "-" + nvl(lastFive);
        } else if ("1".equals(other)) {
            return "+" + nvl(numberCountry) + " " + nvl(intlNumber);
        } else {
            return "";
        }
    }

    // ── Public API ───────────────────────────────────────────────────────────

    /**
     * Encodes the supplied FormData into five pipe-delimited barcode strings.
     *
     * @param d a populated FormData instance
     * @return String[5] where index 0 = barcode 1 … index 4 = barcode 5
     */
    public static String[] encode(FormData d) {
        return new String[]{
            barcode1(d),
            barcode2(d),
            barcode3(d),
            barcode4(d),
            barcode5(d)
        };
    }

    // ── Barcode builders ─────────────────────────────────────────────────────

    private static String barcode1(FormData d) {
        StringBuilder sb = new StringBuilder();

        // Header
        sb.append("IMM1294_06-2018_1|");

        // Personal
        append(sb, d.ServiceIn);
        append(sb, d.UCIClientID);
        append(sb, d.FamilyName);
        append(sb, d.GivenName);
        append(sb, d.AliasFamilyName);
        append(sb, d.AliasGivenName);
        append(sb, d.Sex);
        append(sb, d.DOBYear);
        append(sb, d.DOBMonth);
        append(sb, d.DOBDay);
        append(sb, d.PlaceBirthCity);
        append(sb, d.PlaceBirthCountry);
        append(sb, d.Citizenship);

        // Current COR
        append(sb, d.CurrentCOR_Country);
        append(sb, d.CurrentCOR_Status);
        append(sb, d.CurrentCOR_Other);
        append(sb, d.COR_FromYr);
        append(sb, d.COR_FromMM);
        append(sb, d.COR_FromDD);
        append(sb, d.COR_ToYr);
        append(sb, d.COR_ToMM);
        append(sb, d.COR_ToDD);

        // Previous COR
        append(sb, d.PCRIndicator);
        append(sb, d.PrevCOR1_Country);
        append(sb, d.PrevCOR1_Status);
        append(sb, d.PrevCOR1_Other);
        append(sb, d.PrevCOR2_Country);
        append(sb, d.PrevCOR2_Status);
        append(sb, d.PrevCOR2_Other);

        // Previous COR date ranges (using the PrevCOR fields for the date ranges)
        append(sb, d.PrevCOR1_FromYr);
        append(sb, d.PrevCOR1_FromMM);
        append(sb, d.PrevCOR1_FromDD);
        append(sb, d.PrevCOR1_ToYr);
        append(sb, d.PrevCOR1_ToMM);
        append(sb, d.PrevCOR1_ToDD);
        append(sb, d.PrevCOR2_FromYr);
        append(sb, d.PrevCOR2_FromMM);
        append(sb, d.PrevCOR2_FromDD);
        append(sb, d.PrevCOR2_ToYr);
        append(sb, d.PrevCOR2_ToMM);
        append(sb, d.PrevCOR2_ToDD);

        // Country Where Applying
        append(sb, d.SameAsCORIndicator);
        append(sb, d.CWA_Country);
        append(sb, d.CWA_Status);
        append(sb, d.CWA_Other);
        append(sb, d.CWA_FromYr);
        append(sb, d.CWA_FromMM);
        append(sb, d.CWA_FromDD);
        append(sb, d.CWA_ToYr);
        append(sb, d.CWA_ToMM);
        append(sb, d.CWA_ToDD);

        // Marital Status
        append(sb, d.MaritalStatus);
        append(sb, d.Marriage_Yr);
        append(sb, d.Marriage_MM);
        append(sb, d.Marriage_DD);
        append(sb, d.Spouse_FamilyName);
        append(sb, d.Spouse_GivenName);

        // Previous Marriage indicator
        append(sb, d.PrevMarriedIndicator);

        // Validation date
        append(sb, d.DateLastValidated_Year);
        append(sb, d.DateLastValidated_Month);
        append(sb, d.DateLastValidated_Day);

        return sb.toString();
    }

    private static String barcode2(FormData d) {
        StringBuilder sb = new StringBuilder();

        // Header
        sb.append("IMM1294_06-2018_2|");

        // Previous spouse
        append(sb, d.PrevSpouse_FamilyName);
        append(sb, d.PrevSpouse_GivenName);
        append(sb, d.TypeOfRelationship);
        append(sb, d.PrevMarried_FromYr);
        append(sb, d.PrevMarried_FromMM);
        append(sb, d.PrevMarried_FromDD);
        append(sb, d.PrevMarried_ToYr);
        append(sb, d.PrevMarried_ToMM);
        append(sb, d.PrevMarried_ToDD);
        append(sb, d.PrevSpouse_DOBYear);
        append(sb, d.PrevSpouse_DOBMonth);
        append(sb, d.PrevSpouse_DOBDay);

        // Passport
        append(sb, d.PassportNum);
        append(sb, d.Passport_CountryOfIssue);
        append(sb, d.Passport_IssueYYYY);
        append(sb, d.Passport_IssueMM);
        append(sb, d.Passport_IssueDD);
        append(sb, d.Passport_ExpiryYYYY);
        append(sb, d.Passport_ExpiryMM);
        append(sb, d.Passport_ExpiryDD);
        append(sb, d.TaiwanPIN);
        append(sb, d.IsraelPassportIndicator);

        // Mailing address
        append(sb, d.POBox);
        append(sb, d.AptUnit);
        append(sb, d.StreetNum);
        append(sb, d.Streetname);
        append(sb, d.CityTown);
        append(sb, d.Contact_Country);
        append(sb, d.ProvinceState);
        append(sb, d.PostalCode);
        append(sb, d.District);
        append(sb, d.SameAsMailingIndicator);

        // Residential address
        append(sb, d.Res_AptUnit);
        append(sb, d.Res_StreetNum);
        append(sb, d.Res_StreetName);
        append(sb, d.Res_CityTown);
        append(sb, d.Res_Country);
        append(sb, d.Res_ProvinceState);
        append(sb, d.Res_PostalCode);
        append(sb, d.Res_District);

        // Phone 1
        String phone1Actual = phoneActualNumber(
                d.Phone1_CanadaUS, d.Phone1_Other,
                d.Phone1_AreaCode, d.Phone1_FirstThree, d.Phone1_LastFive,
                d.Phone1_NumberCountry, d.Phone1_IntlNumber);
        append(sb, d.Phone1_Type);
        append(sb, phone1Actual);

        // Phone 2
        String phone2Actual = phoneActualNumber(
                d.Phone2_CanadaUS, d.Phone2_Other,
                d.Phone2_AreaCode, d.Phone2_FirstThree, d.Phone2_LastFive,
                d.Phone2_NumberCountry, d.Phone2_IntlNumber);
        append(sb, d.Phone2_Type);
        append(sb, phone2Actual);

        // Fax
        String faxActual = phoneActualNumber(
                d.Fax_CanadaUS, d.Fax_Other,
                d.Fax_AreaCode, d.Fax_FirstThree, d.Fax_LastFive,
                d.Fax_NumberCountry, d.Fax_IntlNumber);
        append(sb, faxActual);

        // Email
        append(sb, d.Email);

        return sb.toString();
    }

    private static String barcode3(FormData d) {
        StringBuilder sb = new StringBuilder();

        // Header
        sb.append("IMM1294_06-2018_3|");

        // Education
        append(sb, d.EducationIndicator);
        append(sb, d.Edu1_FromYear);
        append(sb, d.Edu1_FromMonth);
        append(sb, d.Edu1_ToYear);
        append(sb, d.Edu1_ToMonth);
        append(sb, d.Edu1_FieldOfStudy);
        append(sb, d.Edu1_School);
        append(sb, d.Edu1_CityTown);
        append(sb, d.Edu1_Country);
        append(sb, d.Edu1_ProvState);

        // Occupation 1
        append(sb, d.Occ1_FromYear);
        append(sb, d.Occ1_FromMonth);
        append(sb, d.Occ1_ToYear);
        append(sb, d.Occ1_ToMonth);
        append(sb, d.Occ1_Occupation);
        append(sb, d.Occ1_Employer);
        append(sb, d.Occ1_CityTown);
        append(sb, d.Occ1_Country);
        append(sb, d.Occ1_ProvState);

        // Occupation 2
        append(sb, d.Occ2_FromYear);
        append(sb, d.Occ2_FromMonth);
        append(sb, d.Occ2_ToYear);
        append(sb, d.Occ2_ToMonth);
        append(sb, d.Occ2_Occupation);
        append(sb, d.Occ2_Employer);
        append(sb, d.Occ2_CityTown);
        append(sb, d.Occ2_Country);
        append(sb, d.Occ2_ProvState);

        // Occupation 3
        append(sb, d.Occ3_FromYear);
        append(sb, d.Occ3_FromMonth);
        append(sb, d.Occ3_ToYear);
        append(sb, d.Occ3_ToMonth);
        append(sb, d.Occ3_Occupation);
        append(sb, d.Occ3_Employer);
        append(sb, d.Occ3_CityTown);
        append(sb, d.Occ3_Country);
        append(sb, d.Occ3_ProvState);

        return sb.toString();
    }

    private static String barcode4(FormData d) {
        StringBuilder sb = new StringBuilder();

        // Header
        sb.append("IMM1294_06-2018_4|");

        // Background
        append(sb, d.BG_HealthChoice);
        append(sb, d.BG_OrgChoice);
        append(sb, d.BG_MedicalDetails);
        append(sb, d.BG_VisaChoice1);
        append(sb, d.BG_VisaChoice2);
        append(sb, d.BG_VisaChoice3);
        append(sb, d.BG_RefusedDetails);
        append(sb, d.BG_CriminalChoice);
        append(sb, d.BG_CriminalDetails);
        append(sb, d.BG_MilitaryChoice);
        append(sb, d.BG_MilitaryDetails);
        append(sb, d.BG_OccupationChoice);
        append(sb, d.BG_GovPositionChoice);

        return sb.toString();
    }

    private static String barcode5(FormData d) {
        StringBuilder sb = new StringBuilder();

        // Header
        sb.append("IMM1294_06-2018_5|");

        // Languages
        append(sb, d.NativeLanguage);
        append(sb, "");             // empty LOV field
        append(sb, d.AbleToCommunicate);
        append(sb, d.LanguageTest);

        // Study details
        append(sb, d.SchoolName);
        append(sb, d.DLI);
        append(sb, d.StudentNo);
        append(sb, d.StudyProvince);
        append(sb, d.StudyCityTown);
        append(sb, d.SchoolAddress);
        append(sb, d.StudyLevel);
        append(sb, d.StudyProgram);
        append(sb, d.Study_FromDate);
        append(sb, d.Study_ToDate);

        // Finances
        append(sb, d.Tuition);
        append(sb, d.RoomBoard);
        append(sb, d.OtherExpenses);
        append(sb, d.Funds);
        append(sb, d.ExpensesPaidBy);
        append(sb, d.ExpensesPaidOther);

        // National ID
        append(sb, d.natIDIndicator);
        append(sb, d.NatID_DocNum);
        append(sb, d.NatID_CountryOfIssue);
        append(sb, d.NatID_IssueDate);
        append(sb, d.NatID_ExpiryDate);

        // US card
        append(sb, d.usCardIndicator);
        append(sb, d.USCard_DocNum);
        append(sb, d.USCard_ExpiryDate);

        // Reader info
        append(sb, d.ReaderInfo);

        return sb.toString();
    }

    // ── main: smoke-test with testData ───────────────────────────────────────

    public static void main(String[] args) {
        FormData d = FormData.testData();
        String[] barcodes = encode(d);

        for (int i = 0; i < barcodes.length; i++) {
            System.out.println("=== Barcode " + (i + 1) + " ===");
            System.out.println(barcodes[i]);
            System.out.println();
        }
    }
}
