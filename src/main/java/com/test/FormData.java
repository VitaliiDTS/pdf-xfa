package com.test;

public class FormData {

    // ── Personal
    public String ServiceIn = "";
    public String UCIClientID = "";
    public String FamilyName = "";
    public String GivenName = "";
    public String AliasFamilyName = "";
    public String AliasGivenName = "";
    public String AliasNameIndicator = "";
    public String Sex = "";
    public String DOBYear = "";
    public String DOBMonth = "";
    public String DOBDay = "";
    public String PlaceBirthCity = "";
    public String PlaceBirthCountry = "";
    public String Citizenship = "";

    // ── Current COR
    public String CurrentCOR_Country = "";
    public String CurrentCOR_Status = "";
    public String CurrentCOR_Other = "";
    public String COR_FromYr = "";
    public String COR_FromMM = "";
    public String COR_FromDD = "";
    public String COR_ToYr = "";
    public String COR_ToMM = "";
    public String COR_ToDD = "";

    // ── Previous COR
    public String PCRIndicator = "";
    public String PrevCOR1_Country = "";
    public String PrevCOR1_Status = "";
    public String PrevCOR1_Other = "";
    public String PrevCOR1_FromYr = "";
    public String PrevCOR1_FromMM = "";
    public String PrevCOR1_FromDD = "";
    public String PrevCOR1_ToYr = "";
    public String PrevCOR1_ToMM = "";
    public String PrevCOR1_ToDD = "";
    public String PrevCOR2_Country = "";
    public String PrevCOR2_Status = "";
    public String PrevCOR2_Other = "";
    public String PrevCOR2_FromYr = "";
    public String PrevCOR2_FromMM = "";
    public String PrevCOR2_FromDD = "";
    public String PrevCOR2_ToYr = "";
    public String PrevCOR2_ToMM = "";
    public String PrevCOR2_ToDD = "";

    // ── Country Where Applying
    public String SameAsCORIndicator = "";
    public String CWA_Country = "";
    public String CWA_Status = "";
    public String CWA_Other = "";
    public String CWA_FromYr = "";
    public String CWA_FromMM = "";
    public String CWA_FromDD = "";
    public String CWA_ToYr = "";
    public String CWA_ToMM = "";
    public String CWA_ToDD = "";

    // ── Marital Status
    public String MaritalStatus = "";
    public String Marriage_Yr = "";
    public String Marriage_MM = "";
    public String Marriage_DD = "";
    public String Spouse_FamilyName = "";
    public String Spouse_GivenName = "";

    // ── Previous Marriage
    public String PrevMarriedIndicator = "";
    public String PrevSpouse_FamilyName = "";
    public String PrevSpouse_GivenName = "";
    public String TypeOfRelationship = "";
    public String PrevMarried_FromYr = "";
    public String PrevMarried_FromMM = "";
    public String PrevMarried_FromDD = "";
    public String PrevMarried_ToYr = "";
    public String PrevMarried_ToMM = "";
    public String PrevMarried_ToDD = "";
    public String PrevSpouse_DOBYear = "";
    public String PrevSpouse_DOBMonth = "";
    public String PrevSpouse_DOBDay = "";

    // ── Validation date
    public String DateLastValidated_Year = "";
    public String DateLastValidated_Month = "";
    public String DateLastValidated_Day = "";

    // ── Languages
    public String NativeLanguage = "";
    public String AbleToCommunicate = "";
    public String LanguageTest = "";

    // ── Passport
    public String PassportNum = "";
    public String Passport_CountryOfIssue = "";
    public String Passport_IssueYYYY = "";
    public String Passport_IssueMM = "";
    public String Passport_IssueDD = "";
    public String Passport_ExpiryYYYY = "";
    public String Passport_ExpiryMM = "";
    public String Passport_ExpiryDD = "";
    public String TaiwanPIN = "";
    public String IsraelPassportIndicator = "";

    // ── National ID / US card
    public String natIDIndicator = "";
    public String NatID_DocNum = "";
    public String NatID_CountryOfIssue = "";
    public String NatID_IssueDate = "";
    public String NatID_ExpiryDate = "";
    public String usCardIndicator = "";
    public String USCard_DocNum = "";
    public String USCard_ExpiryDate = "";

    // ── Mailing address
    public String POBox = "";
    public String AptUnit = "";
    public String StreetNum = "";
    public String Streetname = "";
    public String CityTown = "";
    public String Contact_Country = "";
    public String ProvinceState = "";
    public String PostalCode = "";
    public String District = "";
    public String SameAsMailingIndicator = "";

    // ── Residential address (if different from mailing)
    public String Res_AptUnit = "";
    public String Res_StreetNum = "";
    public String Res_StreetName = "";
    public String Res_CityTown = "";
    public String Res_Country = "";
    public String Res_ProvinceState = "";
    public String Res_PostalCode = "";
    public String Res_District = "";

    // ── Phone 1
    public String Phone1_Type = "";
    public String Phone1_CanadaUS = "";
    public String Phone1_Other = "";
    public String Phone1_AreaCode = "";
    public String Phone1_FirstThree = "";
    public String Phone1_LastFive = "";
    public String Phone1_NumberCountry = "";
    public String Phone1_IntlNumber = "";
    public String Phone1_Ext = "";

    // ── Phone 2
    public String Phone2_Type = "";
    public String Phone2_CanadaUS = "";
    public String Phone2_Other = "";
    public String Phone2_AreaCode = "";
    public String Phone2_FirstThree = "";
    public String Phone2_LastFive = "";
    public String Phone2_NumberCountry = "";
    public String Phone2_IntlNumber = "";

    // ── Fax / Email
    public String Fax_CanadaUS = "";
    public String Fax_Other = "";
    public String Fax_AreaCode = "";
    public String Fax_FirstThree = "";
    public String Fax_LastFive = "";
    public String Fax_NumberCountry = "";
    public String Fax_IntlNumber = "";
    public String Email = "";

    // ── Study details
    public String SchoolName = "";
    public String StudyProgram = "";
    public String StudyLevel = "";
    public String StudyProvince = "";
    public String StudyCityTown = "";
    public String SchoolAddress = "";
    public String Study_FromDate = "";
    public String Study_ToDate = "";
    public String DLI = "";
    public String StudentNo = "";

    // ── Finances
    public String Tuition = "";
    public String RoomBoard = "";
    public String OtherExpenses = "";
    public String Funds = "";
    public String ExpensesPaidBy = "";
    public String ExpensesPaidOther = "";

    // ── Education
    public String EducationIndicator = "";
    public String Edu1_FromYear = "";
    public String Edu1_FromMonth = "";
    public String Edu1_ToYear = "";
    public String Edu1_ToMonth = "";
    public String Edu1_FieldOfStudy = "";
    public String Edu1_School = "";
    public String Edu1_CityTown = "";
    public String Edu1_Country = "";
    public String Edu1_ProvState = "";

    // ── Occupation (3 rows)
    public String Occ1_FromYear = "";
    public String Occ1_FromMonth = "";
    public String Occ1_ToYear = "";
    public String Occ1_ToMonth = "";
    public String Occ1_Occupation = "";
    public String Occ1_Employer = "";
    public String Occ1_CityTown = "";
    public String Occ1_Country = "";
    public String Occ1_ProvState = "";
    public String Occ2_FromYear = "";
    public String Occ2_FromMonth = "";
    public String Occ2_ToYear = "";
    public String Occ2_ToMonth = "";
    public String Occ2_Occupation = "";
    public String Occ2_Employer = "";
    public String Occ2_CityTown = "";
    public String Occ2_Country = "";
    public String Occ2_ProvState = "";
    public String Occ3_FromYear = "";
    public String Occ3_FromMonth = "";
    public String Occ3_ToYear = "";
    public String Occ3_ToMonth = "";
    public String Occ3_Occupation = "";
    public String Occ3_Employer = "";
    public String Occ3_CityTown = "";
    public String Occ3_Country = "";
    public String Occ3_ProvState = "";

    // ── Background
    public String BG_HealthChoice = "";
    public String BG_OrgChoice = "";
    public String BG_MedicalDetails = "";
    public String BG_VisaChoice1 = "";
    public String BG_VisaChoice2 = "";
    public String BG_VisaChoice3 = "";
    public String BG_RefusedDetails = "";
    public String BG_CriminalChoice = "";
    public String BG_CriminalDetails = "";
    public String BG_MilitaryChoice = "";
    public String BG_MilitaryDetails = "";
    public String BG_OccupationChoice = "";
    public String BG_GovPositionChoice = "";

    // ── Consent / misc
    public String Consent0_Choice = "";
    public String ReaderInfo = "";

    // ── Static factory: pre-filled test data
    public static FormData testData() {
        FormData d = new FormData();

        // Personal
        d.ServiceIn = "01";
        d.FamilyName = "KOVALENKO";
        d.GivenName = "OLEKSANDR";
        d.Sex = "M";
        d.DOBYear = "1995";
        d.DOBMonth = "03";
        d.DOBDay = "15";
        d.PlaceBirthCity = "Kyiv";
        d.PlaceBirthCountry = "UKR";
        d.Citizenship = "UKR";

        // Current COR
        d.CurrentCOR_Country = "UKR";
        d.CurrentCOR_Status = "Citizen";
        d.COR_FromYr = "1995";
        d.COR_FromMM = "03";
        d.COR_FromDD = "15";

        // Previous COR
        d.PCRIndicator = "N";

        // Country Where Applying
        d.SameAsCORIndicator = "Y";

        // Marital Status
        d.MaritalStatus = "1";

        // Previous Marriage
        d.PrevMarriedIndicator = "N";

        // Validation date
        d.DateLastValidated_Year = "2026";
        d.DateLastValidated_Month = "03";
        d.DateLastValidated_Day = "16";

        // Languages
        d.NativeLanguage = "Ukrainian";
        d.AbleToCommunicate = "Neither";
        d.LanguageTest = "0";

        // Passport
        d.PassportNum = "FE123456";
        d.Passport_CountryOfIssue = "UKR";
        d.Passport_IssueYYYY = "2020";
        d.Passport_IssueMM = "06";
        d.Passport_IssueDD = "10";
        d.Passport_ExpiryYYYY = "2030";
        d.Passport_ExpiryMM = "06";
        d.Passport_ExpiryDD = "09";
        d.IsraelPassportIndicator = "0";

        // National ID / US card
        d.natIDIndicator = "0";
        d.usCardIndicator = "0";

        // Mailing address
        d.AptUnit = "12";
        d.StreetNum = "45";
        d.Streetname = "Khreshchatyk St";
        d.CityTown = "Kyiv";
        d.Contact_Country = "UKR";
        d.PostalCode = "01001";
        d.SameAsMailingIndicator = "1";

        // Phone 1
        d.Phone1_Type = "Mobile";
        d.Phone1_Other = "1";
        d.Phone1_NumberCountry = "380";
        d.Phone1_IntlNumber = "671234567";

        // Email
        d.Email = "oleksandr.kovalenko@email.com";

        // Study details
        d.SchoolName = "University of Toronto";
        d.StudyProgram = "Computer Science";
        d.StudyLevel = "4";
        d.StudyProvince = "06";
        d.StudyCityTown = "3812";
        d.SchoolAddress = "27 King's College Circle";
        d.Study_FromDate = "2026-09-01";
        d.Study_ToDate = "2029-04-30";
        d.DLI = "O123456789012";

        // Finances
        d.Tuition = "12000";
        d.RoomBoard = "10000";
        d.OtherExpenses = "3000";
        d.Funds = "40000";
        d.ExpensesPaidBy = "Myself";

        // Education
        d.EducationIndicator = "1";
        d.Edu1_FromYear = "2010";
        d.Edu1_FromMonth = "09";
        d.Edu1_ToYear = "2012";
        d.Edu1_ToMonth = "06";
        d.Edu1_FieldOfStudy = "Computer Science";
        d.Edu1_School = "Kyiv Polytechnic Institute";
        d.Edu1_CityTown = "Kyiv";
        d.Edu1_Country = "UKR";

        // Occupation
        d.Occ1_FromYear = "2018";
        d.Occ1_FromMonth = "06";
        d.Occ1_ToYear = "2024";
        d.Occ1_ToMonth = "08";
        d.Occ1_Occupation = "Software Developer";
        d.Occ1_Employer = "Tech Company Ltd";
        d.Occ1_CityTown = "Kyiv";
        d.Occ1_Country = "UKR";

        // Background
        d.BG_HealthChoice = "N";
        d.BG_OrgChoice = "N";
        d.BG_VisaChoice1 = "N";
        d.BG_VisaChoice2 = "N";
        d.BG_VisaChoice3 = "N";
        d.BG_CriminalChoice = "N";
        d.BG_MilitaryChoice = "N";
        d.BG_OccupationChoice = "N";
        d.BG_GovPositionChoice = "N";

        // Consent
        d.Consent0_Choice = "N";

        return d;
    }
}
