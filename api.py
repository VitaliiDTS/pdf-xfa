#!/usr/bin/env python3
"""
Flask REST API — Canadian immigration PDF generator.

## Install
    pip install flask flask-cors

## Run directly
    python api.py

## Run as Windows service via NSSM
    1. Download NSSM: https://nssm.cc/download
    2. Open cmd as Administrator:
       nssm install pdf-xfa-api
         Path:              C:\Python314\python.exe
         Arguments:         C:\pdf-xfa\api.py
         Startup directory: C:\pdf-xfa
    3. nssm start pdf-xfa-api

## Endpoints
    POST /generate   — { "form": "<name>", ...fields }  → PDF download
    GET  /forms      — list available forms and their mode
    GET  /health     — {"status": "ok"}

## Supported forms
    imm1294  — Study Permit Application         (validate mode)
    imm5257  — Temporary Resident Visa          (validate mode)
    imm5645  — Family Information               (fill mode)
    imm1295e — Work Permit Application          (validate mode)
    imm5646  — Custodian Declaration            (validate mode)
    imm5707  — Family Information (PR/EE)       (fill mode)
    imm5709  — Study Permit Extension           (validate mode)
    imm5710  — Work Permit Extension            (validate mode)
    imm5713  — Family Member Representative     (fill mode, AcroForm/PyMuPDF)

## Mode detection
    If forms/<name>/button.png exists → validate mode (Acrobat)
    Otherwise                         → fill mode (APDFL only)

## Environment variables
    PDF_XFA_ROOT     — project root (default: C:\\pdf-xfa)
    API_PORT         — port (default: 5000)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import os
import glob
import html
import json
import base64
import subprocess
import threading
from datetime import date

import fitz  # PyMuPDF

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Ensure prints appear immediately in the console (no stdout buffering)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.environ.get('PDF_XFA_ROOT', os.path.dirname(os.path.abspath(__file__)))
PORT         = int(os.environ.get('API_PORT', 5000))

def _find_mvn():
    import shutil
    found = shutil.which('mvn') or shutil.which('mvn.cmd')
    if found:
        return found
    candidates = [
        r'C:\ProgramData\chocolatey\lib\maven\apache-maven-3.9.14\bin\mvn.cmd',
        r'C:\apache-maven\bin\mvn.cmd',
        r'C:\maven\bin\mvn.cmd',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError('mvn not found — set MVN env var or add Maven to PATH')

MVN   = os.environ.get('MVN', _find_mvn())
_lock = threading.Lock()

app = Flask(__name__)
CORS(app)

# ── Load form choices (extracted from XFA PDFs) ───────────────────────────────
_CHOICES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'form_choices.json')
try:
    with open(_CHOICES_PATH, encoding='utf-8') as _f:
        _FORM_CHOICES = json.load(_f)
except Exception as _e:
    print(f'[api] Warning: could not load form_choices.json: {_e}')
    _FORM_CHOICES = {}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _v(d, key, default=''):
    return html.escape(str(d.get(key, default)))

def _split_date(d, key):
    val = d.get(key, '')
    if val and len(val) >= 10:
        return val[:4], val[5:7], val[8:10]
    return '', '', ''

def _split_ym(d, key):
    val = d.get(key, '')
    if val and len(val) >= 7:
        return val[:4], val[5:7]
    return '', ''


# ── XML builders ──────────────────────────────────────────────────────────────
def build_xml_imm1294(d):
    today = date.today()
    v = lambda k, default='': _v(d, k, default)
    dob_yr,   dob_mm,   dob_dd   = _split_date(d, 'dob')
    cor_yr,   cor_mm,   cor_dd   = _split_date(d, 'cor_from')
    pi_yr,    pi_mm,    pi_dd    = _split_date(d, 'passport_issue')
    pe_yr,    pe_mm,    pe_dd    = _split_date(d, 'passport_expiry')
    edu_yr,   edu_mm             = _split_ym(d, 'edu_from')
    edu_tyr,  edu_tmm            = _split_ym(d, 'edu_to')
    job_yr,   job_mm             = _split_ym(d, 'job_from')
    job_tyr,  job_tmm            = _split_ym(d, 'job_to')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data>
<form1>
<Page1>
  <Header><CRCNum>0</CRCNum></Header>
  <PersonalDetails>
    <ServiceIn><ServiceIn>{v('service_in','01')}</ServiceIn></ServiceIn>
    <VisaType><VisaType/></VisaType>
    <UCIClientID>{v('uci')}</UCIClientID>
    <Name><FamilyName>{v('family_name')}</FamilyName><GivenName>{v('given_name')}</GivenName></Name>
    <AliasName>
      <AliasFamilyName>{v('alias_family')}</AliasFamilyName>
      <AliasGivenName>{v('alias_given')}</AliasGivenName>
      <AliasNameIndicator><AliasNameIndicator>{v('alias_indicator','0')}</AliasNameIndicator></AliasNameIndicator>
    </AliasName>
    <Sex><Sex>{v('sex')}</Sex></Sex>
    <DOBYear>{dob_yr}</DOBYear><DOBMonth>{dob_mm}</DOBMonth><DOBDay>{dob_dd}</DOBDay>
    <PlaceBirthCity>{v('birth_city')}</PlaceBirthCity>
    <PlaceBirthCountry>{v('birth_country')}</PlaceBirthCountry>
    <Citizenship><Citizenship>{v('citizenship')}</Citizenship></Citizenship>
    <CurrentCOR><Row2><Country>{v('cor_country')}</Country><Status>{v('cor_status')}</Status><Other/><FromDate>{v('cor_from')}</FromDate><ToDate/></Row2></CurrentCOR>
    <CORDates><FromYr>{cor_yr}</FromYr><FromMM>{cor_mm}</FromMM><FromDD>{cor_dd}</FromDD><ToYr/><ToMM/><ToDD/></CORDates>
    <PCRIndicator>N</PCRIndicator>
    <SameAsCORIndicator>{v('same_as_cor','Y')}</SameAsCORIndicator>
    <CountryWhereApplying><Row2><Country/><Status/><Other/><FromDate/><ToDate/></Row2></CountryWhereApplying>
    <CWADates><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></CWADates>
    <ApplicationValidatedFlag></ApplicationValidatedFlag>
  </PersonalDetails>
  <MaritalStatus><SectionA>
    <MaritalStatus>{v('marital_status')}</MaritalStatus>
    <DateOfMarriage/><MarriageDate><FromYr/><FromMM/><FromDD/></MarriageDate>
    <FamilyName>{v('spouse_family')}</FamilyName><GivenName>{v('spouse_given')}</GivenName>
  </SectionA></MaritalStatus>
</Page1>
<Page2>
  <MaritalStatus><SectionA>
    <PrevMarriedIndicator>{v('prev_married','N')}</PrevMarriedIndicator>
    <DateLastValidated><DateCalc/><Year>{today.year}</Year><Month>{today.month:02d}</Month><Day>{today.day:02d}</Day></DateLastValidated>
    <PMFamilyName/><PrevSpouseDOB><DOBYear/><DOBMonth/><DOBDay/></PrevSpouseDOB>
    <GivenName><PMGivenName/></GivenName><TypeOfRelationship/><FromDate/><ToDate><ToDate/></ToDate>
    <PreviouslyMarriedDates><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></PreviouslyMarriedDates>
    <Languages>
      <languages>
        <nativeLang><nativeLang>{v('native_lang')}</nativeLang></nativeLang>
        <ableToCommunicate><ableToCommunicate>{v('communicate')}</ableToCommunicate></ableToCommunicate>
        <lov/>
      </languages>
      <LanguageTest>{v('lang_test','0')}</LanguageTest>
    </Languages>
    <Passport>
      <PassportNum><PassportNum>{v('passport_num')}</PassportNum></PassportNum>
      <CountryofIssue><CountryofIssue>{v('passport_country')}</CountryofIssue></CountryofIssue>
      <IssueDate><IssueDate>{v('passport_issue')}</IssueDate></IssueDate>
      <ExpiryDate>{v('passport_expiry')}</ExpiryDate>
      <IssueYYYY>{pi_yr}</IssueYYYY><IssueMM>{pi_mm}</IssueMM><IssueDD>{pi_dd}</IssueDD>
      <expiryYYYY>{pe_yr}</expiryYYYY><expiryMM>{pe_mm}</expiryMM><expiryDD>{pe_dd}</expiryDD>
      <TaiwanPIN/><IsraelPassportIndicator>0</IsraelPassportIndicator>
    </Passport>
  </SectionA></MaritalStatus>
  <natID><q1><natIDIndicator>0</natIDIndicator></q1></natID>
  <USCard><q1><usCardIndicator>0</usCardIndicator></q1></USCard>
  <contact>
    <AddressRow1>
      <POBox><POBox/></POBox>
      <Apt><AptUnit>{v('apt')}</AptUnit></Apt>
      <StreetNum><StreetNum>{v('street_num')}</StreetNum></StreetNum>
      <Streetname><Streetname>{v('street_name')}</Streetname></Streetname>
    </AddressRow1>
    <AddressRow2>
      <CityTow><CityTown>{v('city')}</CityTown></CityTow>
      <Country><Country>{v('country')}</Country></Country>
      <ProvinceState><ProvinceState>{v('province')}</ProvinceState></ProvinceState>
      <PostalCode><PostalCode>{v('postal_code')}</PostalCode></PostalCode>
      <District/>
    </AddressRow2>
    <SameAsMailingIndicator>1</SameAsMailingIndicator>
  </contact>
</Page2>
<Page3>
  <PhoneNumbers>
    <Phone>
      <Type>Mobile</Type><CanadaUS>0</CanadaUS><Other>1</Other><NumberExt/>
      <NumberCountry>{v('phone_country_code')}</NumberCountry><ActualNumber/>
      <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
      <IntlNumber><IntlNumber>{v('phone_number')}</IntlNumber></IntlNumber>
    </Phone>
    <AltPhone><Type/><CanadaUS>0</CanadaUS><Other>0</Other><NumberExt/><NumberCountry/><ActualNumber/>
      <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber><IntlNumber><IntlNumber/></IntlNumber>
    </AltPhone>
  </PhoneNumbers>
  <FaxEmail>
    <Phone><CanadaUS>0</CanadaUS><Other>0</Other><NumberExt/><NumberCountry/><ActualNumber/>
      <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber><IntlNumber><IntlNumber/></IntlNumber>
    </Phone>
    <Email>{v('email')}</Email>
  </FaxEmail>
  <DetailsOfStudy><PurposeRow1>
    <schoolName>
      <SchoolName>{v('school_name')}</SchoolName>
      <Program>{v('program')}</Program>
      <Level>{v('study_level')}</Level>
    </schoolName>
    <ProvinceState><Prov>{v('school_province')}</Prov></ProvinceState>
    <CityTown><CityTown>{v('school_city')}</CityTown></CityTown>
    <Address><Address>{v('school_address')}</Address></Address>
    <HowLongStudy><FromDate>{v('study_from')}</FromDate><ToDate>{v('study_to')}</ToDate></HowLongStudy>
    <DLI>{v('dli')}</DLI><StudentNo/>
  </PurposeRow1></DetailsOfStudy>
  <Contacts_Row1>
    <tuition><amount>{v('tuition')}</amount></tuition>
    <roomBoard><amount>{v('room_board')}</amount></roomBoard>
    <other><amount>{v('other_costs')}</amount></other>
    <expensesPaid>
      <Funds><Funds>{v('funds')}</Funds></Funds>
      <expensesPaidBy>{v('expenses_paid_by')}</expensesPaidBy>
      <Other/>
    </expensesPaid>
  </Contacts_Row1>
  <Education>
    <EducationIndicator>{v('edu_indicator')}</EducationIndicator>
    <Edu_Row1>
      <FromYear>{edu_yr}</FromYear><FromMonth>{edu_mm}</FromMonth>
      <ToYear>{edu_tyr}</ToYear><ToMonth>{edu_tmm}</ToMonth>
      <FieldOfStudy>{v('edu_field')}</FieldOfStudy><School>{v('edu_school')}</School>
      <CityTown>{v('edu_city')}</CityTown>
      <Country><Country>{v('edu_country')}</Country></Country><ProvState/>
    </Edu_Row1>
  </Education>
  <Occupation><OccupationRow1>
    <FromYear>{job_yr}</FromYear><FromMonth>{job_mm}</FromMonth>
    <ToYear>{job_tyr}</ToYear><ToMonth>{job_tmm}</ToMonth>
    <Occupation><Occupation>{v('occupation')}</Occupation></Occupation>
    <Employer>{v('employer')}</Employer>
    <CityTown><CityTown>{v('job_city')}</CityTown></CityTown>
    <Country><Country>{v('job_country')}</Country></Country><ProvState/>
  </OccupationRow1></Occupation>
</Page3>
<Page4>
  <BackgroundInfo><Choice>{v('health_a','N')}</Choice><Choice>{v('health_b','N')}</Choice><Details><MedicalDetails>{v('medical_details')}</MedicalDetails></Details></BackgroundInfo>
  <PageWrapper>
    <BackgroundInfo2><VisaChoice1>{v('refused_visa','N')}</VisaChoice1><VisaChoice2>{v('refused_entry','N')}</VisaChoice2><Details><refusedDetails>{v('refused_details')}</refusedDetails></Details><VisaChoice3>{v('removed_deported','N')}</VisaChoice3></BackgroundInfo2>
    <BackgroundInfo3><Choice>{v('criminal','N')}</Choice><Details>{v('criminal_details')}</Details></BackgroundInfo3>
    <Military><Choice>{v('military','N')}</Choice><militaryServiceDetails>{v('military_details')}</militaryServiceDetails></Military>
    <Occupation><Choice>{v('occupation_choice','N')}</Choice></Occupation>
    <GovPosition><Choice>{v('gov_position','N')}</Choice></GovPosition>
  </PageWrapper>
  <Consent0><Choice>N</Choice></Consent0>
</Page4>
</form1>
</xfa:data>
</xfa:datasets>'''


def build_xml_imm5257(d):
    today = date.today()
    v = lambda k, default='': _v(d, k, default)
    dob_yr,  dob_mm,  dob_dd  = _split_date(d, 'dob')
    pi_yr,   pi_mm,   pi_dd   = _split_date(d, 'passport_issue')
    pe_yr,   pe_mm,   pe_dd   = _split_date(d, 'passport_expiry')
    vf_yr,   vf_mm,   vf_dd   = _split_date(d, 'visit_from')
    vt_yr,   vt_mm,   vt_dd   = _split_date(d, 'visit_to')
    edu_yr,  edu_mm            = _split_ym(d, 'edu_from')
    edu_tyr, edu_tmm           = _split_ym(d, 'edu_to')
    job_yr,  job_mm            = _split_ym(d, 'job_from')
    job_tyr, job_tmm           = _split_ym(d, 'job_to')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data>
<form1>
<Page1>
  <Header><CRCNum>0</CRCNum></Header>
  <PersonalDetails>
    <UCIClientID>{v('uci')}</UCIClientID>
    <ServiceIn><ServiceIn>{v('service_in','01')}</ServiceIn></ServiceIn>
    <VisaType><VisaType>{v('visa_type','VisitorVisa')}</VisaType></VisaType>
    <Name><FamilyName>{v('family_name')}</FamilyName><GivenName>{v('given_name')}</GivenName></Name>
    <AliasName>
      <AliasFamilyName>{v('alias_family')}</AliasFamilyName>
      <AliasGivenName>{v('alias_given')}</AliasGivenName>
      <AliasNameIndicator><AliasNameIndicator>{v('alias_indicator','N')}</AliasNameIndicator></AliasNameIndicator>
    </AliasName>
    <Sex><Sex>{v('sex')}</Sex></Sex>
    <DOBYear>{dob_yr}</DOBYear><DOBMonth>{dob_mm}</DOBMonth><DOBDay>{dob_dd}</DOBDay>
    <PlaceBirthCity>{v('birth_city')}</PlaceBirthCity>
    <PlaceBirthCountry>{v('birth_country')}</PlaceBirthCountry>
    <Citizenship><Citizenship>{v('citizenship')}</Citizenship></Citizenship>
    <CurrentCOR><Row2><Country>{v('cor_country')}</Country><Status>{v('cor_status')}</Status><Other/><FromDate/><ToDate/></Row2></CurrentCOR>
    <CORDates><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></CORDates>
    <PCRIndicator>N</PCRIndicator>
    <PreviousCOR><Row2><Country/><Status/><Other/><FromDate/><ToDate/></Row2><Row3><Country/><Status/><Other/><FromDate/><ToDate/></Row3></PreviousCOR>
    <PCRDatesR1><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></PCRDatesR1>
    <PCRDatesR2><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></PCRDatesR2>
    <SameAsCORIndicator>{v('same_as_cor','Y')}</SameAsCORIndicator>
    <CountryWhereApplying><Row2><Country/><Status/><Other/><FromDate/><ToDate/></Row2></CountryWhereApplying>
    <CWADates><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></CWADates>
    <ApplicationValidatedFlag></ApplicationValidatedFlag>
  </PersonalDetails>
  <MaritalStatus><SectionA>
    <MaritalStatus>{v('marital_status')}</MaritalStatus>
    <DateOfMarriage>{v('marriage_date')}</DateOfMarriage>
    <MarriageDate><FromYr>{v('marriage_date')[:4] if d.get('marriage_date') else ''}</FromYr><FromMM>{v('marriage_date')[5:7] if d.get('marriage_date') else ''}</FromMM><FromDD>{v('marriage_date')[8:10] if d.get('marriage_date') else ''}</FromDD></MarriageDate>
    <FamilyName>{v('spouse_family')}</FamilyName><GivenName>{v('spouse_given')}</GivenName>
  </SectionA></MaritalStatus>
</Page1>
<Page2>
  <MaritalStatus><SectionA>
    <PrevMarriedIndicator>{v('prev_married','N')}</PrevMarriedIndicator>
    <DateLastValidated><DateCalc/><Year>{today.year}</Year><Month>{today.month:02d}</Month><Day>{today.day:02d}</Day></DateLastValidated>
    <PMFamilyName>{v('prev_spouse_family')}</PMFamilyName><GivenName><PMGivenName>{v('prev_spouse_given')}</PMGivenName></GivenName>
    <PrevSpouseDOB><DOBYear>{v('prev_spouse_dob','').split('-')[0] if v('prev_spouse_dob') else ''}</DOBYear><DOBMonth>{v('prev_spouse_dob','').split('-')[1] if len(v('prev_spouse_dob','').split('-'))>1 else ''}</DOBMonth><DOBDay>{v('prev_spouse_dob','').split('-')[2] if len(v('prev_spouse_dob','').split('-'))>2 else ''}</DOBDay></PrevSpouseDOB>
    <TypeOfRelationship>{v('prev_relationship_type')}</TypeOfRelationship>
    <FromDate>{v('prev_marriage_from')}</FromDate><ToDate><ToDate>{v('prev_marriage_to')}</ToDate></ToDate>
    <PreviouslyMarriedDates><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></PreviouslyMarriedDates>
    <Passport>
      <PassportNum><PassportNum>{v('passport_num')}</PassportNum></PassportNum>
      <CountryofIssue><CountryofIssue>{v('passport_country')}</CountryofIssue></CountryofIssue>
      <IssueDate><IssueDate>{v('passport_issue')}</IssueDate></IssueDate>
      <ExpiryDate>{v('passport_expiry')}</ExpiryDate>
      <IssueYYYY>{pi_yr}</IssueYYYY><IssueMM>{pi_mm}</IssueMM><IssueDD>{pi_dd}</IssueDD>
      <expiryYYYY>{pe_yr}</expiryYYYY><expiryMM>{pe_mm}</expiryMM><expiryDD>{pe_dd}</expiryDD>
      <TaiwanPIN/><IsraelPassportIndicator/>
    </Passport>
    <Languages>
      <languages>
        <nativeLang><nativeLang>{v('native_lang')}</nativeLang></nativeLang>
        <ableToCommunicate><ableToCommunicate>{v('communicate')}</ableToCommunicate></ableToCommunicate>
        <lov/>
      </languages>
      <LanguageTest>{v('lang_test','N')}</LanguageTest>
    </Languages>
  </SectionA></MaritalStatus>
  <natID><q1><natIDIndicator>{v('nat_id_indicator','N')}</natIDIndicator></q1>
    <natIDdocs>
      <DocNum><DocNum>{v('nat_id_num')}</DocNum></DocNum>
      <CountryofIssue><CountryofIssue>{v('nat_id_country')}</CountryofIssue></CountryofIssue>
      <IssueDate><IssueDate>{v('nat_id_issue')}</IssueDate></IssueDate>
      <ExpiryDate>{v('nat_id_expiry')}</ExpiryDate>
    </natIDdocs>
  </natID>
  <USCard>
    <q1><usCardIndicator>{v('us_card_indicator','N')}</usCardIndicator></q1>
    <usCarddocs><DocNum><DocNum>{v('us_card_num')}</DocNum></DocNum><ExpiryDate>{v('us_card_expiry')}</ExpiryDate></usCarddocs>
  </USCard>
  <ContactInformation><contact>
    <AddressRow1>
      <POBox><POBox/></POBox>
      <Apt><AptUnit>{v('apt')}</AptUnit></Apt>
      <StreetNum><StreetNum>{v('street_num')}</StreetNum></StreetNum>
      <Streetname><Streetname>{v('street_name')}</Streetname></Streetname>
    </AddressRow1>
    <AddressRow2>
      <CityTow><CityTown>{v('city')}</CityTown></CityTow>
      <Country><Country>{v('country')}</Country></Country>
      <ProvinceState><ProvinceState>{v('province')}</ProvinceState></ProvinceState>
      <PostalCode><PostalCode>{v('postal_code')}</PostalCode></PostalCode>
      <District/>
    </AddressRow2>
    <SameAsMailingIndicator>{v('same_as_mailing','Y')}</SameAsMailingIndicator>
    <ResidentialAddressRow1>
      <AptUnit><AptUnit>{v('resi_apt')}</AptUnit></AptUnit>
      <StreetNum><StreetNum>{v('resi_street_num')}</StreetNum></StreetNum>
      <StreetName><Streetname>{v('resi_street_name')}</Streetname></StreetName>
      <CityTown><CityTown>{v('resi_city')}</CityTown></CityTown>
    </ResidentialAddressRow1>
    <ResidentialAddressRow2>
      <Country><Country>{v('resi_country')}</Country></Country>
      <ProvinceState><ProvinceState>{v('resi_province')}</ProvinceState></ProvinceState>
      <PostalCode><PostalCode>{v('resi_postal_code')}</PostalCode></PostalCode>
      <District/>
    </ResidentialAddressRow2>
    <PhoneNumbers>
      <Phone>
        <Type>02</Type><CanadaUS>0</CanadaUS><Other>1</Other><NumberExt/>
        <NumberCountry>{v('phone_country_code')}</NumberCountry>
        <ActualNumber>{v('phone_actual')}</ActualNumber>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
        <IntlNumber><IntlNumber>{v('phone_number')}</IntlNumber></IntlNumber>
      </Phone>
      <AltPhone><Type/><CanadaUS>0</CanadaUS><Other>0</Other><NumberExt/><NumberCountry/><ActualNumber/>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber><IntlNumber><IntlNumber/></IntlNumber>
      </AltPhone>
    </PhoneNumbers>
    <FaxEmail>
      <Phone><CanadaUS>0</CanadaUS><Other>0</Other><NumberExt/><NumberCountry/><ActualNumber/>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber><IntlNumber><IntlNumber/></IntlNumber>
      </Phone>
      <Email>{v('email')}</Email>
    </FaxEmail>
  </contact></ContactInformation>
</Page2>
<Page3>
  <DetailsOfVisit><PurposeRow1>
    <PurposeOfVisit><PurposeOfVisit>{v('purpose','02')}</PurposeOfVisit></PurposeOfVisit>
    <Other><Other>{v('purpose_other')}</Other></Other>
    <HowLongStay>
      <FromDate>{v('visit_from')}</FromDate>
      <ToDate>{v('visit_to')}</ToDate>
      <StayDates><FromYr>{vf_yr}</FromYr><FromMM>{vf_mm}</FromMM><FromDD>{vf_dd}</FromDD><ToYr>{vt_yr}</ToYr><ToMM>{vt_mm}</ToMM><ToDD>{vt_dd}</ToDD></StayDates>
    </HowLongStay>
    <Funds><Funds>{v('funds')}</Funds></Funds>
  </PurposeRow1>
  <Contacts_Row1>
    <Name><Name>{v('canada_contact_name')}</Name></Name>
    <RelationshipToMe><RelationshipToMe>{v('canada_contact_relationship')}</RelationshipToMe></RelationshipToMe>
    <AddressInCanada><AddressInCanada>{v('canada_contact_address','TBA')}</AddressInCanada></AddressInCanada>
  </Contacts_Row1>
  </DetailsOfVisit>
  <Contacts_Row2><Name><Name/></Name><Relationship><RelationshipToMe/></Relationship><AddressInCanada><AddressInCanada/></AddressInCanada></Contacts_Row2>
  <Education>
    <EducationIndicator>{v('edu_indicator','N')}</EducationIndicator>
    <Edu_Row1>
      <FromYear>{edu_yr}</FromYear><FromMonth>{edu_mm}</FromMonth>
      <ToYear>{edu_tyr}</ToYear><ToMonth>{edu_tmm}</ToMonth>
      <FieldOfStudy>{v('edu_field')}</FieldOfStudy><School>{v('edu_school')}</School>
      <CityTown>{v('edu_city')}</CityTown>
      <Country><Country>{v('edu_country')}</Country></Country><ProvState/>
    </Edu_Row1>
  </Education>
  <Occupation><OccupationRow1>
    <FromYear>{job_yr}</FromYear><FromMonth>{job_mm}</FromMonth>
    <ToYear>{job_tyr}</ToYear><ToMonth>{job_tmm}</ToMonth>
    <Occupation><Occupation>{v('occupation')}</Occupation></Occupation>
    <Employer>{v('employer')}</Employer>
    <CityTown><CityTown>{v('job_city')}</CityTown></CityTown>
    <Country><Country>{v('job_country')}</Country></Country><ProvState/>
  </OccupationRow1>
  <OccupationRow2><FromYear/><FromMonth/><ToYear/><ToMonth/><Occupation><Occupation/></Occupation><Employer/><CityTown><CityTown/></CityTown><Country><Country/></Country><ProvState/></OccupationRow2>
  <OccupationRow3><FromYear/><FromMonth/><ToYear/><ToMonth/><Occupation><Occupation/></Occupation><Employer/><CityTown><CityTown/></CityTown><Country><Country/></Country><ProvState/></OccupationRow3>
  </Occupation>
  <BackgroundInfo><Choice>{v('health_a','N')}</Choice><Choice>{v('health_b','N')}</Choice><Details><MedicalDetails>{v('medical_details')}</MedicalDetails></Details></BackgroundInfo>
  <BackgroundInfo2><VisaChoice1>{v('refused_visa','N')}</VisaChoice1><VisaChoice2>{v('refused_entry','N')}</VisaChoice2><Details><refusedDetails>{v('refused_details')}</refusedDetails><VisaChoice3>{v('removed_deported','N')}</VisaChoice3></Details></BackgroundInfo2>
  <PageWrapper>
    <BackgroundInfo3><Choice>{v('criminal','N')}</Choice><details>{v('criminal_details')}</details></BackgroundInfo3>
    <Military><Choice>{v('military','N')}</Choice><militaryServiceDetails>{v('military_details')}</militaryServiceDetails></Military>
    <Occupation><Choice>{v('occupation_choice','N')}</Choice></Occupation>
    <GovPosition><Choice>{v('gov_position','N')}</Choice></GovPosition>
  </PageWrapper>
  <Signature>
    <Consent0><Choice>Y</Choice></Consent0>
    <C1CertificateIssueDate>{today.isoformat()}</C1CertificateIssueDate>
    <TextField2/>
  </Signature>
</Page3>
</form1>
</xfa:data>
</xfa:datasets>'''


def build_xml_imm5645(d):
    v = lambda k, default='': _v(d, k, default)

    def child_xml(c):
        yes = '1' if c.get('accompanying') else '0'
        no  = '0' if c.get('accompanying') else '1'
        return f'''<Child>
      <ChildName>{c.get('name','')}</ChildName>
      <ChildMStatus>{c.get('marital_status','6')}</ChildMStatus>
      <ChildRelationship>{c.get('relationship','')}</ChildRelationship>
      <ChildDOB>{c.get('dob','')}</ChildDOB>
      <ChildCOB>{c.get('cob','')}</ChildCOB>
      <ChildAddress>{c.get('address','')}</ChildAddress>
      <ChildOccupation>{c.get('occupation','')}</ChildOccupation>
      <ChildYes>{yes}</ChildYes>
      <ChildNo>{no}</ChildNo>
    </Child>'''

    def empty_child():
        return '<Child><ChildName/><ChildMStatus/><ChildRelationship/><ChildDOB/><ChildCOB/><ChildAddress/><ChildOccupation/><ChildYes>0</ChildYes><ChildNo>0</ChildNo></Child>'

    app_type = d.get('app_type', 'visitor')
    visitor = '1' if app_type == 'visitor' else '0'
    worker  = '1' if app_type == 'worker'  else '0'
    student = '1' if app_type == 'student' else '0'
    other   = '1' if app_type == 'other'   else '0'

    children_b = d.get('children', [])
    children_c = d.get('siblings', [])

    # Pad to minimum slots
    b_slots = max(4, len(children_b))
    c_slots = max(7, len(children_c))
    b_xml = ''.join(child_xml(c) for c in children_b) + empty_child() * (b_slots - len(children_b))
    c_xml = ''.join(child_xml(c) for c in children_c) + empty_child() * (c_slots - len(children_c))

    spouse_yes = '1' if d.get('spouse_accompanying') else '0'
    spouse_no  = '0' if d.get('spouse_accompanying') else '1'
    mother_yes = '1' if d.get('mother_accompanying') else '0'
    mother_no  = '0' if d.get('mother_accompanying') else '1'
    father_yes = '1' if d.get('father_accompanying') else '0'
    father_no  = '0' if d.get('father_accompanying') else '1'

    today = date.today()

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data>
<IMM_5645>
<page1>
  <Subform1>
    <Visitor>{visitor}</Visitor><Worker>{worker}</Worker><Student>{student}</Student><Other>{other}</Other>
  </Subform1>
  <SectionA>
    <Applicant>
      <AppName>{v('app_name')}</AppName>
      <AppDOB>{v('app_dob')}</AppDOB>
      <AppCOB>{v('app_cob')}</AppCOB>
      <AppAddress>{v('app_address')}</AppAddress>
      <AppOccupation>{v('app_occupation')}</AppOccupation>
      <ChildMStatus>{v('app_marital_status','5')}</ChildMStatus>
    </Applicant>
    <Spouse>
      <SpouseName>{v('spouse_name')}</SpouseName>
      <SpouseDOB>{v('spouse_dob')}</SpouseDOB>
      <SpouseCOB>{v('spouse_cob')}</SpouseCOB>
      <SpouseAddress>{v('spouse_address')}</SpouseAddress>
      <SpouseOccupation>{v('spouse_occupation')}</SpouseOccupation>
      <SpouseYes>{spouse_yes}</SpouseYes><SpouseNo>{spouse_no}</SpouseNo>
      <ChildMStatus>{v('spouse_marital_status','5')}</ChildMStatus>
    </Spouse>
    <Mother>
      <MotherName>{v('mother_name')}</MotherName>
      <MotherDOB>{v('mother_dob')}</MotherDOB>
      <MotherCOB>{v('mother_cob')}</MotherCOB>
      <MotherAddress>{v('mother_address')}</MotherAddress>
      <MotherOccupation>{v('mother_occupation')}</MotherOccupation>
      <MotherYes>{mother_yes}</MotherYes><MotherNo>{mother_no}</MotherNo>
      <ChildMStatus>{v('mother_marital_status','5')}</ChildMStatus>
    </Mother>
    <Father>
      <FatherName>{v('father_name')}</FatherName>
      <FatherDOB>{v('father_dob')}</FatherDOB>
      <FatherCOB>{v('father_cob')}</FatherCOB>
      <FatherAddress>{v('father_address')}</FatherAddress>
      <FatherOccupation>{v('father_occupation')}</FatherOccupation>
      <FatherYes>{father_yes}</FatherYes><FatherNo>{father_no}</FatherNo>
      <ChildMStatus>{v('father_marital_status','5')}</ChildMStatus>
    </Father>
    <SectionAsignature/><SectionAdate>{today.isoformat()}</SectionAdate>
  </SectionA>
  <SectionB>
    {b_xml}
    <SectionBsignature/><SectionBdate/>
  </SectionB>
  <SectionC>
    {c_xml}
    <SectionCsignature/><SectionCdate>{today.isoformat()}</SectionCdate>
  </SectionC>
</page1>
<num>1</num><totPage>2</totPage><FormNumber>IMM 5645 (01-2021) E</FormNumber>
<num>2</num><totPage>2</totPage><FormNumber>IMM 5645 (01-2021) E</FormNumber>
</IMM_5645>
</xfa:data>
</xfa:datasets>'''


def build_xml_imm1295e(d):
    today = date.today()
    v = lambda k, default='': _v(d, k, default)
    dob_yr,  dob_mm,  dob_dd  = _split_date(d, 'dob')
    pi_yr,   pi_mm,   pi_dd   = _split_date(d, 'passport_issue')
    pe_yr,   pe_mm,   pe_dd   = _split_date(d, 'passport_expiry')
    edu_yr,  edu_mm            = _split_ym(d, 'edu_from')
    edu_tyr, edu_tmm           = _split_ym(d, 'edu_to')
    job_yr,  job_mm            = _split_ym(d, 'job_from')
    cor_yr,  cor_mm,  cor_dd   = _split_date(d, 'cor_from')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data>
<form1>
<Page1>
  <Header><CRCNum>0</CRCNum></Header>
  <Age></Age>
  <AdultFlag>adult</AdultFlag>
  <FormVersion>.ENU-10-2019</FormVersion>
  <PrevSpouseAge/>
  <PersonalDetails>
    <ServiceIn><ServiceIn>{v('service_in','01')}</ServiceIn></ServiceIn>
    <VisaType><VisaType>{v('visa_type','WorkPermit')}</VisaType></VisaType>
    <UCIClientID>{v('uci')}</UCIClientID>
    <Name><FamilyName>{v('family_name')}</FamilyName><GivenName>{v('given_name')}</GivenName></Name>
    <AliasName>
      <AliasFamilyName>{v('alias_family')}</AliasFamilyName>
      <AliasGivenName>{v('alias_given')}</AliasGivenName>
      <AliasNameIndicator><AliasNameIndicator>{v('alias_indicator','N')}</AliasNameIndicator></AliasNameIndicator>
    </AliasName>
    <Sex><Sex>{v('sex')}</Sex></Sex>
    <DOBYear>{dob_yr}</DOBYear><DOBMonth>{dob_mm}</DOBMonth><DOBDay>{dob_dd}</DOBDay>
    <PlaceBirthCity>{v('birth_city')}</PlaceBirthCity>
    <PlaceBirthCountry>{v('birth_country')}</PlaceBirthCountry>
    <Citizenship><Citizenship>{v('citizenship')}</Citizenship></Citizenship>
    <CurrentCOR><Row2><Country>{v('cor_country')}</Country><Status>{v('cor_status')}</Status><Other/><FromDate/><ToDate/></Row2></CurrentCOR>
    <CORDates><FromYr>{cor_yr}</FromYr><FromMM>{cor_mm}</FromMM><FromDD>{cor_dd}</FromDD><ToYr/><ToMM/><ToDD/></CORDates>
    <PCRIndicator>N</PCRIndicator>
    <PreviousCOR><Row2><Country/><Status/><Other/><FromDate/><ToDate/></Row2><Row3><Country/><Status/><Other/><FromDate/><ToDate/></Row3></PreviousCOR>
    <PCRDatesR1><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></PCRDatesR1>
    <PCRDatesR2><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></PCRDatesR2>
    <SameAsCORIndicator>{v('same_as_cor','Y')}</SameAsCORIndicator>
    <CountryWhereApplying><Row2><Country/><Status/><Other/><FromDate/><ToDate/></Row2></CountryWhereApplying>
    <CWADates><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></CWADates>
    <ApplicationValidatedFlag></ApplicationValidatedFlag>
  </PersonalDetails>
  <MaritalStatus><SectionA>
    <MaritalStatus>{v('marital_status','1')}</MaritalStatus>
    <DateOfMarriage/><MarriageDate><FromYr/><FromMM/><FromDD/></MarriageDate>
    <FamilyName>{v('spouse_family')}</FamilyName><GivenName>{v('spouse_given')}</GivenName>
  </SectionA></MaritalStatus>
</Page1>
<Page2>
  <MaritalStatus><SectionA>
    <PrevMarriedIndicator>{v('prev_married','N')}</PrevMarriedIndicator>
    <DateLastValidated><DateCalc/><Year>{today.year}</Year><Month>{today.month:02d}</Month><Day>{today.day:02d}</Day></DateLastValidated>
    <PMFamilyName>{v('prev_spouse_family')}</PMFamilyName><GivenName><PMGivenName>{v('prev_spouse_given')}</PMGivenName></GivenName>
    <PrevSpouseDOB><DOBYear>{v('prev_spouse_dob','').split('-')[0] if v('prev_spouse_dob') else ''}</DOBYear><DOBMonth>{v('prev_spouse_dob','').split('-')[1] if len(v('prev_spouse_dob','').split('-'))>1 else ''}</DOBMonth><DOBDay>{v('prev_spouse_dob','').split('-')[2] if len(v('prev_spouse_dob','').split('-'))>2 else ''}</DOBDay></PrevSpouseDOB>
    <TypeOfRelationship>{v('prev_relationship_type')}</TypeOfRelationship>
    <FromDate>{v('prev_marriage_from')}</FromDate><ToDate><ToDate>{v('prev_marriage_to')}</ToDate></ToDate>
    <PreviouslyMarriedDates><FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/></PreviouslyMarriedDates>
    <Languages>
      <languages>
        <nativeLang><nativeLang>{v('native_lang')}</nativeLang></nativeLang>
        <ableToCommunicate><ableToCommunicate>{v('communicate')}</ableToCommunicate></ableToCommunicate>
        <lov/>
      </languages>
      <LanguageTest>{v('lang_test','N')}</LanguageTest>
    </Languages>
    <Passport>
      <PassportNum><PassportNum>{v('passport_num')}</PassportNum></PassportNum>
      <CountryofIssue><CountryofIssue>{v('passport_country')}</CountryofIssue></CountryofIssue>
      <IssueDate><IssueDate>{v('passport_issue')}</IssueDate></IssueDate>
      <ExpiryDate>{v('passport_expiry')}</ExpiryDate>
      <IssueYYYY>{pi_yr}</IssueYYYY><IssueMM>{pi_mm}</IssueMM><IssueDD>{pi_dd}</IssueDD>
      <expiryYYYY>{pe_yr}</expiryYYYY><expiryMM>{pe_mm}</expiryMM><expiryDD>{pe_dd}</expiryDD>
      <TaiwanPIN/><IsraelPassportIndicator/>
    </Passport>
  </SectionA></MaritalStatus>
  <natID><q1><natIDIndicator>{v('nat_id_indicator','N')}</natIDIndicator></q1>
    <natIDdocs>
      <DocNum><DocNum>{v('nat_id_num')}</DocNum></DocNum>
      <CountryofIssue><CountryofIssue>{v('nat_id_country')}</CountryofIssue></CountryofIssue>
      <IssueDate><IssueDate>{v('nat_id_issue')}</IssueDate></IssueDate>
      <ExpiryDate>{v('nat_id_expiry')}</ExpiryDate>
    </natIDdocs>
  </natID>
  <USCard>
    <q1><usCardIndicator>{v('us_card_indicator','N')}</usCardIndicator></q1>
    <usCarddocs><DocNum><DocNum>{v('us_card_num')}</DocNum></DocNum><ExpiryDate>{v('us_card_expiry')}</ExpiryDate></usCarddocs>
  </USCard>
  <ContactInformation><contact>
    <AddressRow1>
      <POBox><POBox/></POBox>
      <Apt><AptUnit>{v('apt')}</AptUnit></Apt>
      <StreetNum><StreetNum>{v('street_num')}</StreetNum></StreetNum>
      <Streetname><Streetname>{v('street_name')}</Streetname></Streetname>
    </AddressRow1>
    <AddressRow2>
      <CityTow><CityTown>{v('city')}</CityTown></CityTow>
      <Country><Country>{v('country')}</Country></Country>
      <ProvinceState><ProvinceState>{v('province')}</ProvinceState></ProvinceState>
      <PostalCode><PostalCode>{v('postal_code')}</PostalCode></PostalCode>
      <District/>
    </AddressRow2>
    <SameAsMailingIndicator>{v('same_as_mailing','Y')}</SameAsMailingIndicator>
    <ResidentialAddressRow1>
      <AptUnit><AptUnit>{v('resi_apt')}</AptUnit></AptUnit>
      <StreetNum><StreetNum>{v('resi_street_num')}</StreetNum></StreetNum>
      <StreetName><Streetname>{v('resi_street_name')}</Streetname></StreetName>
      <CityTown><CityTown>{v('resi_city')}</CityTown></CityTown>
    </ResidentialAddressRow1>
    <ResidentialAddressRow2>
      <Country><Country>{v('resi_country')}</Country></Country>
      <ProvinceState><ProvinceState>{v('resi_province')}</ProvinceState></ProvinceState>
      <PostalCode><PostalCode>{v('resi_postal_code')}</PostalCode></PostalCode>
      <District/>
    </ResidentialAddressRow2>
    <PhoneNumbers>
      <Phone>
        <Type>02</Type><CanadaUS>0</CanadaUS><Other>1</Other><NumberExt/>
        <NumberCountry>{v('phone_country_code')}</NumberCountry>
        <ActualNumber>{v('phone_actual')}</ActualNumber>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
        <IntlNumber><IntlNumber>{v('phone_number')}</IntlNumber></IntlNumber>
      </Phone>
      <AltPhone><Type/><CanadaUS>0</CanadaUS><Other>0</Other><NumberExt/><NumberCountry/><ActualNumber/>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber><IntlNumber><IntlNumber/></IntlNumber>
      </AltPhone>
    </PhoneNumbers>
  </contact></ContactInformation>
</Page2>
<Page3>
  <FaxEmail>
    <Phone><CanadaUS>0</CanadaUS><Other>0</Other><NumberExt/><NumberCountry/><ActualNumber/>
      <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber><IntlNumber><IntlNumber/></IntlNumber>
    </Phone>
    <Email>{v('email')}</Email>
  </FaxEmail>
  <DetailsOfIntendedWork><DetailsOfWork>
    <TypeofWork><WorkPermitType>{v('work_permit_type','01')}</WorkPermitType></TypeofWork>
    <PurposeRow1>
      <EmployerName><EmployerName>{v('employer_name')}</EmployerName></EmployerName>
      <Address><Address>{v('employer_address')}</Address></Address>
    </PurposeRow1>
  </DetailsOfWork></DetailsOfIntendedWork>
  <IntendedLocationInCanada><intendedLocation>
    <ProvinceState><ProvinceState>{v('work_province','06')}</ProvinceState></ProvinceState>
    <CityTown><CityTown>{v('work_city_code','3829')}</CityTown></CityTown>
    <Address>{v('work_address')}</Address>
  </intendedLocation></IntendedLocationInCanada>
  <DetailsOfWorkCont><details>
    <jobTitle>{v('job_title')}</jobTitle>
    <posDesc>{v('job_description')}</posDesc>
    <HowLongStudy>
      <FromDate>{v('work_from')}</FromDate>
      <ToDate>{v('work_to')}</ToDate>
    </HowLongStudy>
    <LMO><LMO>{v('lmo_number')}</LMO></LMO>
  </details></DetailsOfWorkCont>
  <LCP><Caregiver>
    <ChildCare>0</ChildCare><Disabled>0</Disabled><Elderly>0</Elderly><Other>0</Other>
    <checkBoxCalcField/><personsCare><noPersons/></personsCare>
  </Caregiver></LCP>
  <PageWrapper>
    <Education>
      <EducationIndicator>{v('edu_indicator','Y')}</EducationIndicator>
      <Edu_Row1>
        <FromYear>{edu_yr}</FromYear><FromMonth>{edu_mm}</FromMonth>
        <ToYear>{edu_tyr}</ToYear><ToMonth>{edu_tmm}</ToMonth>
        <FieldOfStudy>{v('edu_field')}</FieldOfStudy><School>{v('edu_school')}</School>
        <CityTown>{v('edu_city')}</CityTown>
        <Country><Country>{v('edu_country')}</Country></Country><ProvState/>
      </Edu_Row1>
    </Education>
    <Occupation>
      <OccupationRow1>
        <FromYear>{job_yr}</FromYear><FromMonth>{job_mm}</FromMonth>
        <ToYear/><ToMonth/>
        <Occupation><Occupation>{v('occupation')}</Occupation></Occupation>
        <Employer>{v('employer')}</Employer>
        <CityTown><CityTown>{v('job_city')}</CityTown></CityTown>
        <Country><Country>{v('job_country')}</Country></Country><ProvState/>
      </OccupationRow1>
      <OccupationRow2><FromYear/><FromMonth/><ToYear/><ToMonth/><Occupation><Occupation/></Occupation><Employer/><CityTown><CityTown/></CityTown><Country><Country/></Country><ProvState/></OccupationRow2>
      <OccupationRow3><FromYear/><FromMonth/><ToYear/><ToMonth/><Occupation><Occupation/></Occupation><Employer/><CityTown><CityTown/></CityTown><Country><Country/></Country><ProvState/></OccupationRow3>
    </Occupation>
  </PageWrapper>
</Page3>
<Page4>
  <BackgroundInfo><Details><MedicalDetails>{v('medical_details')}</MedicalDetails></Details><Choice>{v('health_a','N')}</Choice><Choice>{v('health_b','N')}</Choice></BackgroundInfo>
  <BackgroundInfo2><VisaChoice1>{v('refused_visa','N')}</VisaChoice1><VisaChoice2>{v('refused_entry','N')}</VisaChoice2><Details><refusedDetails>{v('refused_details')}</refusedDetails></Details><VisaChoice3>{v('removed_deported','N')}</VisaChoice3></BackgroundInfo2>
  <PageWrapper>
    <BackgroundInfo3><Choice>{v('criminal','N')}</Choice><militaryServiceDetails>{v('criminal_details')}</militaryServiceDetails></BackgroundInfo3>
    <Military><Choice>{v('military','N')}</Choice><militaryServiceDetails>{v('military_details')}</militaryServiceDetails></Military>
    <Occupation><Choice>{v('occupation_choice','N')}</Choice></Occupation>
    <GovPosition><Choice>{v('gov_position','N')}</Choice></GovPosition>
  </PageWrapper>
  <Consent0>
    <Choice>Y</Choice>
    <TextField2/>
    <C1CertificateIssueDate>{today.isoformat()}</C1CertificateIssueDate>
  </Consent0>
</Page4>
</form1>
</xfa:data>
</xfa:datasets>'''


def build_xml_imm5709(d):
    today = date.today()
    v = lambda k, default='': _v(d, k, default)
    dob_yr,    dob_mm,    dob_dd    = _split_date(d, 'dob')
    pi_yr,     pi_mm,     pi_dd     = _split_date(d, 'passport_issue')
    pe_yr,     pe_mm,     pe_dd     = _split_date(d, 'passport_expiry')
    cor_f_yr,  cor_f_mm,  cor_f_dd  = _split_date(d, 'cor_from')
    cor_t_yr,  cor_t_mm,  cor_t_dd  = _split_date(d, 'cor_to')
    pcr1_f_yr, pcr1_f_mm, pcr1_f_dd = _split_date(d, 'prev_cor1_from')
    pcr1_t_yr, pcr1_t_mm, pcr1_t_dd = _split_date(d, 'prev_cor1_to')
    pcr2_f_yr, pcr2_f_mm, pcr2_f_dd = _split_date(d, 'prev_cor2_from')
    pcr2_t_yr, pcr2_t_mm, pcr2_t_dd = _split_date(d, 'prev_cor2_to')
    edu_yr,    edu_mm               = _split_ym(d, 'edu_from')
    edu_tyr,   edu_tmm              = _split_ym(d, 'edu_to')
    job_yr,    job_mm               = _split_ym(d, 'job_from')
    job_tyr,   job_tmm              = _split_ym(d, 'job_to')
    marriage_yr,  marriage_mm,  marriage_dd  = _split_date(d, 'marriage_date')
    pm_f_yr,   pm_f_mm,   pm_f_dd   = _split_date(d, 'prev_marriage_from')
    pm_t_yr,   pm_t_mm,   pm_t_dd   = _split_date(d, 'prev_marriage_to')
    pm_dob_yr, pm_dob_mm, pm_dob_dd = _split_date(d, 'prev_spouse_dob')

    applying_extend  = '1' if d.get('applying_for', 'extend') == 'extend'  else '0'
    applying_restore = '1' if d.get('applying_for', 'extend') == 'restore' else '0'
    applying_trp     = '1' if d.get('applying_for', 'extend') == 'trp'     else '0'

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data>
<form1>
<Page1>
  <Header><CRCNum>0</CRCNum></Header>
  <Age></Age>
  <AdultFlag>adult</AdultFlag>
  <FormVersion>.ENU-01-2024</FormVersion>
  <PrevAge/>
  <PersonalDetails>
    <ApplicationValidatedFlag></ApplicationValidatedFlag>
    <ServiceIn>
      <UCIClientID>{v('uci')}</UCIClientID>
      <ServiceIn>{v('service_in','01')}</ServiceIn>
    </ServiceIn>
    <OfficeUse><ApplicationValidatedFlag></ApplicationValidatedFlag></OfficeUse>
    <ApplyingFor>
      <RestoreStat>{applying_restore}</RestoreStat>
      <Extend>{applying_extend}</Extend>
      <HiddenStat/>
      <TRP>{applying_trp}</TRP>
    </ApplyingFor>
    <Name>
      <FamilyName>{v('family_name')}</FamilyName>
      <GivenName>{v('given_name')}</GivenName>
    </Name>
    <AliasName>
      <AliasFamilyName>{v('alias_family')}</AliasFamilyName>
      <AliasGivenName>{v('alias_given')}</AliasGivenName>
      <AliasNameIndicator><AliasNameIndicator>{v('alias_indicator','N')}</AliasNameIndicator></AliasNameIndicator>
    </AliasName>
    <q3-4-5>
      <sex><Sex>{v('sex')}</Sex></sex>
      <dob>
        <DOBDay>{dob_dd}</DOBDay>
        <DOBMonth>{dob_mm}</DOBMonth>
        <DOBYear>{dob_yr}</DOBYear>
      </dob>
      <pob>
        <PlaceBirthCity>{v('birth_city')}</PlaceBirthCity>
        <PlaceBirthCountry>{v('birth_country')}</PlaceBirthCountry>
      </pob>
    </q3-4-5>
    <Citizenship><Citizenship>{v('citizenship')}</Citizenship></Citizenship>
    <CurrentCOR>
      <CurrentCOR>
        <Row1 xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <Row2>
          <Country>{v('cor_country')}</Country>
          <Status>{v('cor_status')}</Status>
          <Other/>
          <FromDate>{v('cor_from')}</FromDate>
          <ToDate>{v('cor_to')}</ToDate>
        </Row2>
      </CurrentCOR>
      <CORDates>
        <FromYr>{cor_f_yr}</FromYr><FromMM>{cor_f_mm}</FromMM><FromDD>{cor_f_dd}</FromDD>
        <ToDD>{cor_t_dd}</ToDD><ToYr>{cor_t_yr}</ToYr><ToMM>{cor_t_mm}</ToMM>
      </CORDates>
    </CurrentCOR>
    <PrevCOR>
      <PCRIndicator>{v('pcr_indicator','N')}</PCRIndicator>
      <PreviousCOR>
        <Row1 xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <Row2>
          <Country>{v('prev_cor1_country')}</Country><Status>{v('prev_cor1_status')}</Status>
          <Other>{v('prev_cor1_other')}</Other><FromDate>{v('prev_cor1_from')}</FromDate><ToDate>{v('prev_cor1_to')}</ToDate>
        </Row2>
        <Row3>
          <Country>{v('prev_cor2_country')}</Country><Status>{v('prev_cor2_status')}</Status>
          <Other>{v('prev_cor2_other')}</Other><FromDate>{v('prev_cor2_from')}</FromDate><ToDate>{v('prev_cor2_to')}</ToDate>
        </Row3>
      </PreviousCOR>
      <PCRDatesR1><FromYr>{pcr1_f_yr}</FromYr><FromMM>{pcr1_f_mm}</FromMM><FromDD>{pcr1_f_dd}</FromDD><ToYr>{pcr1_t_yr}</ToYr><ToMM>{pcr1_t_mm}</ToMM><ToDD>{pcr1_t_dd}</ToDD></PCRDatesR1>
      <PCRDatesR2><FromYr>{pcr2_f_yr}</FromYr><FromMM>{pcr2_f_mm}</FromMM><FromDD>{pcr2_f_dd}</FromDD><ToYr>{pcr2_t_yr}</ToYr><ToMM>{pcr2_t_mm}</ToMM><ToDD>{pcr2_t_dd}</ToDD></PCRDatesR2>
    </PrevCOR>
  </PersonalDetails>
  <MaritalStatus>
    <Current>
      <MaritalStatus>{v('marital_status')}</MaritalStatus>
      <b>
        <DateOfMarriage>{v('marriage_date')}</DateOfMarriage>
        <MarriageDate><FromYr>{marriage_yr}</FromYr><FromMM>{marriage_mm}</FromMM><FromDD>{marriage_dd}</FromDD></MarriageDate>
      </b>
      <c><FamilyName>{v('spouse_family')}</FamilyName><GivenName>{v('spouse_given')}</GivenName></c>
    </Current>
    <d><SpouseStatus>{v('spouse_status','N')}</SpouseStatus></d>
  </MaritalStatus>
</Page1>
<Page2>
  <MaritalStatus>
    <PrevMarriage>
      <PrevMarriedIndicator>{v('prev_married','N')}</PrevMarriedIndicator>
      <DateLastValidated><DateCalc/><Year/><Month/><Day/></DateLastValidated>
      <PMFamilyName>{v('prev_spouse_family')}</PMFamilyName><PMGivenName>{v('prev_spouse_given')}</PMGivenName>
      <TypeOfRelationship>{v('prev_relationship_type')}</TypeOfRelationship>
      <From><FromDate>{v('prev_marriage_from')}</FromDate></From>
      <To><ToDate>{v('prev_marriage_to')}</ToDate></To>
      <PreviouslyMarriedDates><FromYr>{pm_f_yr}</FromYr><FromMM>{pm_f_mm}</FromMM><FromDD>{pm_f_dd}</FromDD><ToYr>{pm_t_yr}</ToYr><ToMM>{pm_t_mm}</ToMM><ToDD>{pm_t_dd}</ToDD></PreviouslyMarriedDates>
      <dob><DOBDay>{pm_dob_dd}</DOBDay><DOBMonth>{pm_dob_mm}</DOBMonth><DOBYear>{pm_dob_yr}</DOBYear></dob>
    </PrevMarriage>
  </MaritalStatus>
  <Languages>
    <nativeLang>{v('native_lang')}</nativeLang>
    <communicateLang>{v('communicate')}</communicateLang>
    <LangTestIndicator>{v('lang_test','N')}</LangTestIndicator>
    <FreqLang/>
  </Languages>
  <Passport>
    <PassportNum>{v('passport_num')}</PassportNum>
    <CountryofIssue>{v('passport_country')}</CountryofIssue>
    <IssueDate>{v('passport_issue')}</IssueDate>
    <ExpiryDate>{v('passport_expiry')}</ExpiryDate>
    <Issue><YYYY>{pi_yr}</YYYY><MM>{pi_mm}</MM><DD>{pi_dd}</DD></Issue>
    <Expiry><YYYY>{pe_yr}</YYYY><MM>{pe_mm}</MM><DD>{pe_dd}</DD></Expiry>
    <TaiwanPIN/><IsraelPassportIndicator/>
  </Passport>
  <natID>
    <SectionHeader xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <q1><natIDIndicator>{v('nat_id_indicator','N')}</natIDIndicator></q1>
    <natIDdocs>
      <DocNum><DocNum>{v('nat_id_num')}</DocNum></DocNum>
      <CountryofIssue><CountryofIssue>{v('nat_id_country')}</CountryofIssue></CountryofIssue>
      <IssueDate><IssueDate>{v('nat_id_issue')}</IssueDate></IssueDate>
      <ExpiryDate>{v('nat_id_expiry')}</ExpiryDate>
    </natIDdocs>
  </natID>
  <USCard>
    <SectionHeader xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <q1><usCardIndicator>{v('us_card_indicator','N')}</usCardIndicator></q1>
    <usCarddocs>
      <DocNum><DocNum>{v('us_card_num')}</DocNum></DocNum>
      <ExpiryDate>{v('us_card_expiry')}</ExpiryDate>
    </usCarddocs>
  </USCard>
  <ContactInformation>
    <AddrLbl xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <Mailing>
      <text xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
      <AddrLine1>
        <POBox/><AptUnit>{v('apt')}</AptUnit>
        <StreetNum>{v('street_num')}</StreetNum>
        <Streetname>{v('street_name')}</Streetname>
      </AddrLine1>
      <AddrLine2>
        <City>{v('city')}</City>
        <Country>{v('country')}</Country>
        <Prov>{v('province')}</Prov>
        <PostalCode>{v('postal_code')}</PostalCode>
        <District/>
      </AddrLine2>
    </Mailing>
    <Resi>
      <SameAsAddr><SameAsMailingInd>{v('same_as_mailing','Y')}</SameAsMailingInd></SameAsAddr>
      <AddrLine1>
        <AptUnit>{v('resi_apt')}</AptUnit>
        <StreetNum>{v('resi_street_num')}</StreetNum>
        <Streetname>{v('resi_street_name')}</Streetname>
      </AddrLine1>
      <AddrLine2>
        <City>{v('resi_city')}</City>
        <Country>{v('resi_country')}</Country>
        <Prov>{v('resi_province')}</Prov>
        <PostalCode>{v('resi_postal_code')}</PostalCode>
        <District/>
      </AddrLine2>
    </Resi>
    <q3-4>
      <Phone>
        <CanOtherInd><CanadaUS>0</CanadaUS><Other>1</Other></CanOtherInd>
        <ActualNumber/>
        <Type>02</Type><NumberExt/>
        <NumberCountry>{v('phone_country_code')}</NumberCountry>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
        <IntlNumber><IntlNumber>{v('phone_number')}</IntlNumber></IntlNumber>
      </Phone>
      <AltPhone>
        <CanOtherInd><CanadaUS>0</CanadaUS><Other>0</Other></CanOtherInd>
        <ActualNumber/><Type/><NumberExt/><NumberCountry/>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
        <IntlNumber><IntlNumber/></IntlNumber>
      </AltPhone>
    </q3-4>
    <q5-6>
      <Fax>
        <CanOtherInd><CanadaUS>0</CanadaUS><Other>0</Other></CanOtherInd>
        <NumberExt/><NumberCountry/><ActualNumber/>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
        <IntlNumber><IntlNumber/></IntlNumber>
      </Fax>
      <Email><Email>{v('email')}</Email></Email>
    </q5-6>
  </ContactInformation>
</Page2>
<Page3>
  <ComingIntoCda>
    <OrigEntry>
      <DateLastEntry>{v('canada_entry_date')}</DateLastEntry>
      <Place>{v('canada_entry_place')}</Place>
    </OrigEntry>
    <PurposeOfVisit>
      <PurposeOfVisit>{v('visit_purpose','04')}</PurposeOfVisit>
      <Other/>
    </PurposeOfVisit>
    <RecentEntry><DateLastEntry/><Place/></RecentEntry>
    <PrevDocNum><docNum>{v('prev_doc_num')}</docNum></PrevDocNum>
  </ComingIntoCda>
  <DetailsOfStudy>
    <SchoolDetails>
      <SchoolName>{v('school_name')}</SchoolName>
      <Prov>{v('school_province')}</Prov>
      <CityTown>{v('school_city_code')}</CityTown>
      <Address>{v('school_address')}</Address>
      <DLI>{v('dli')}</DLI>
      <StudentNo>{v('student_no')}</StudentNo>
      <StudyTerm>
        <FromDate>{v('study_from')}</FromDate>
        <ToDate>{v('study_to')}</ToDate>
      </StudyTerm>
      <EduCosts>
        <Tuition>{v('tuition')}</Tuition>
        <Room>{v('room_board')}</Room>
        <OtherCosts>{v('other_costs')}</OtherCosts>
      </EduCosts>
      <Funds>
        <ExpPaidBy>{v('expenses_paid_by')}</ExpPaidBy>
        <FundsAvail>{v('funds')}</FundsAvail>
        <Other/>
      </Funds>
      <StudyMajor>
        <Program>{v('study_program')}</Program>
        <Level>{v('study_level')}</Level>
      </StudyMajor>
    </SchoolDetails>
  </DetailsOfStudy>
  <WorkPermit>
    <a><WorkPermit>{v('work_permit','N')}</WorkPermit></a>
    <PermitType>{v('work_permit_type')}</PermitType>
  </WorkPermit>
  <CAQ>
    <CertNum>{v('caq_num')}</CertNum>
    <CertExpiry>{v('caq_expiry')}</CertExpiry>
  </CAQ>
  <Education>
    <EducationIndicator>{v('edu_indicator','Y')}</EducationIndicator>
    <EduLine1>
      <From><YYYY>{edu_yr}</YYYY><MM>{edu_mm}</MM></From>
      <FieldOfStudy>{v('edu_field')}</FieldOfStudy>
      <School>{v('edu_school')}</School>
    </EduLine1>
    <EduLine2>
      <To><YYYY>{edu_tyr}</YYYY><MM>{edu_tmm}</MM></To>
      <City>{v('edu_city')}</City>
      <Country>{v('edu_country')}</Country>
      <Prov>{v('edu_province')}</Prov>
    </EduLine2>
  </Education>
  <Employment>
    <EmpRec1>
      <Line1><From><YYYY>{job_yr}</YYYY><MM>{job_mm}</MM></From><Occupation>{v('occupation')}</Occupation><Employer>{v('employer')}</Employer></Line1>
      <Line2><To><YYYY>{job_tyr}</YYYY><MM>{job_tmm}</MM></To><City>{v('job_city')}</City><Country>{v('job_country')}</Country><ProvState/></Line2>
    </EmpRec1>
    <EmpRec2>
      <Line1><From><YYYY/><MM/></From><Occupation/><Employer/></Line1>
      <Line2><To><YYYY/><MM/></To><City/><Country/><ProvState/></Line2>
    </EmpRec2>
  </Employment>
</Page3>
<Page4>
  <EmpRec3>
    <Line1><From><YYYY/><MM/></From><Occupation/><Employer/></Line1>
    <Line2><To><YYYY/><MM/></To><City/><Country/><ProvState/></Line2>
  </EmpRec3>
  <BackgroundInfo>
    <BackgroundHeader xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <HealthQ><qANY>{v('health_a','N')}</qANY><qBNY>{v('health_b','N')}</qBNY><MedicalDetails>{v('medical_details')}</MedicalDetails><backgroundInfoCalc/></HealthQ>
    <PrevApplied><qANY>{v('prev_applied_a','N')}</qANY><qBNY>{v('prev_applied_b','N')}</qBNY><qCNY>{v('prev_applied_c','N')}</qCNY><refusedDetails>{v('refused_details')}</refusedDetails></PrevApplied>
    <Criminal><qANY>{v('criminal','N')}</qANY><refusedDetails>{v('criminal_details')}</refusedDetails></Criminal>
    <Military><qANY>{v('military','N')}</qANY><militaryServiceDetails>{v('military_details')}</militaryServiceDetails></Military>
    <Occupation><Choice>{v('occupation_choice','N')}</Choice></Occupation>
    <GovPosition><qGovtNY>{v('gov_position','N')}</qGovtNY></GovPosition>
    <Illtreatment><qWitnessNY>{v('illtreatment','N')}</qWitnessNY></Illtreatment>
  </BackgroundInfo>
  <Signature>
    <TextField2/>
    <C1CertificateIssueDate>{today.isoformat()}</C1CertificateIssueDate>
    <FutureComm>{v('future_comm','Y')}</FutureComm>
  </Signature>
  <Important xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
  <ReaderInfo/>
</Page4>
</form1>
</xfa:data>
</xfa:datasets>'''


def build_xml_imm5710(d):
    today = date.today()
    v = lambda k, default='': _v(d, k, default)
    dob_yr,    dob_mm,    dob_dd    = _split_date(d, 'dob')
    pi_yr,     pi_mm,     pi_dd     = _split_date(d, 'passport_issue')
    pe_yr,     pe_mm,     pe_dd     = _split_date(d, 'passport_expiry')
    cor_f_yr,  cor_f_mm,  cor_f_dd  = _split_date(d, 'cor_from')
    cor_t_yr,  cor_t_mm,  cor_t_dd  = _split_date(d, 'cor_to')
    pcr1_f_yr, pcr1_f_mm, pcr1_f_dd = _split_date(d, 'prev_cor1_from')
    pcr1_t_yr, pcr1_t_mm, pcr1_t_dd = _split_date(d, 'prev_cor1_to')
    pcr2_f_yr, pcr2_f_mm, pcr2_f_dd = _split_date(d, 'prev_cor2_from')
    pcr2_t_yr, pcr2_t_mm, pcr2_t_dd = _split_date(d, 'prev_cor2_to')
    edu_yr,    edu_mm               = _split_ym(d, 'edu_from')
    edu_tyr,   edu_tmm              = _split_ym(d, 'edu_to')
    job_yr,    job_mm               = _split_ym(d, 'job_from')
    job_tyr,   job_tmm              = _split_ym(d, 'job_to')
    marriage_yr,  marriage_mm,  marriage_dd  = _split_date(d, 'marriage_date')
    pm_f_yr,   pm_f_mm,   pm_f_dd   = _split_date(d, 'prev_marriage_from')
    pm_t_yr,   pm_t_mm,   pm_t_dd   = _split_date(d, 'prev_marriage_to')
    pm_dob_yr, pm_dob_mm, pm_dob_dd = _split_date(d, 'prev_spouse_dob')

    applying = d.get('applying_for', 'new_employer')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data>
<form1>
<Page1>
  <Header><CRCNum>0</CRCNum></Header>
  <PersonalDetails>
    <ApplicationValidatedFlag></ApplicationValidatedFlag>
    <ServiceIn>
      <UCIClientID>{v('uci')}</UCIClientID>
      <ServiceIn>{v('service_in','01')}</ServiceIn>
    </ServiceIn>
    <ApplyingFor>
      <RestoreStat>{'1' if applying == 'restore' else '0'}</RestoreStat>
      <Extend>{'1' if applying == 'extend' else '0'}</Extend>
      <NewEmployer>{'1' if applying == 'new_employer' else '0'}</NewEmployer>
      <TRP>{'1' if applying == 'trp' else '0'}</TRP>
    </ApplyingFor>
    <Name>
      <FamilyName>{v('family_name')}</FamilyName>
      <GivenName>{v('given_name')}</GivenName>
    </Name>
    <AliasName>
      <AliasFamilyName>{v('alias_family')}</AliasFamilyName>
      <AliasGivenName>{v('alias_given')}</AliasGivenName>
      <AliasNameIndicator><AliasNameIndicator>{v('alias_indicator','N')}</AliasNameIndicator></AliasNameIndicator>
    </AliasName>
    <q3-4-5>
      <sex><Sex>{v('sex')}</Sex></sex>
      <dob><DOBDay>{dob_dd}</DOBDay><DOBMonth>{dob_mm}</DOBMonth><DOBYear>{dob_yr}</DOBYear></dob>
      <pob><PlaceBirthCity>{v('birth_city')}</PlaceBirthCity><PlaceBirthCountry>{v('birth_country')}</PlaceBirthCountry></pob>
    </q3-4-5>
    <Citizenship><Citizenship>{v('citizenship')}</Citizenship></Citizenship>
    <CurrentCOR>
      <CurrentCOR>
        <Row1 xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <Row2><Country>{v('cor_country')}</Country><Status>{v('cor_status')}</Status><Other/><FromDate>{v('cor_from')}</FromDate><ToDate>{v('cor_to')}</ToDate></Row2>
      </CurrentCOR>
      <CORDates>
        <FromYr>{cor_f_yr}</FromYr><FromMM>{cor_f_mm}</FromMM><FromDD>{cor_f_dd}</FromDD>
        <ToDD>{cor_t_dd}</ToDD><ToYr>{cor_t_yr}</ToYr><ToMM>{cor_t_mm}</ToMM>
      </CORDates>
    </CurrentCOR>
    <PrevCOR>
      <PCRIndicator>{v('pcr_indicator','N')}</PCRIndicator>
      <PreviousCOR>
        <Row1 xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <Row2>
          <Country>{v('prev_cor1_country')}</Country><Status>{v('prev_cor1_status')}</Status>
          <Other>{v('prev_cor1_other')}</Other><FromDate>{v('prev_cor1_from')}</FromDate><ToDate>{v('prev_cor1_to')}</ToDate>
        </Row2>
        <Row3>
          <Country>{v('prev_cor2_country')}</Country><Status>{v('prev_cor2_status')}</Status>
          <Other>{v('prev_cor2_other')}</Other><FromDate>{v('prev_cor2_from')}</FromDate><ToDate>{v('prev_cor2_to')}</ToDate>
        </Row3>
      </PreviousCOR>
      <PCRDatesR1><FromYr>{pcr1_f_yr}</FromYr><FromMM>{pcr1_f_mm}</FromMM><FromDD>{pcr1_f_dd}</FromDD><ToYr>{pcr1_t_yr}</ToYr><ToMM>{pcr1_t_mm}</ToMM><ToDD>{pcr1_t_dd}</ToDD></PCRDatesR1>
      <PCRDatesR2><FromYr>{pcr2_f_yr}</FromYr><FromMM>{pcr2_f_mm}</FromMM><FromDD>{pcr2_f_dd}</FromDD><ToYr>{pcr2_t_yr}</ToYr><ToMM>{pcr2_t_mm}</ToMM><ToDD>{pcr2_t_dd}</ToDD></PCRDatesR2>
    </PrevCOR>
  </PersonalDetails>
  <MaritalStatus>
    <Current>
      <MaritalStatus>{v('marital_status')}</MaritalStatus>
      <b>
        <DateOfMarriage>{v('marriage_date')}</DateOfMarriage>
        <MarriageDate><FromYr>{marriage_yr}</FromYr><FromMM>{marriage_mm}</FromMM><FromDD>{marriage_dd}</FromDD></MarriageDate>
      </b>
      <c><FamilyName>{v('spouse_family')}</FamilyName><GivenName>{v('spouse_given')}</GivenName></c>
    </Current>
    <d><SpouseStatus>{v('spouse_status','N')}</SpouseStatus></d>
  </MaritalStatus>
</Page1>
<Page2>
  <MaritalStatus>
    <PrevMarriage>
      <PrevMarriedIndicator>{v('prev_married','N')}</PrevMarriedIndicator>
      <DateLastValidated><DateCalc/><Year/><Month/><Day/></DateLastValidated>
      <PMFamilyName>{v('prev_spouse_family')}</PMFamilyName><PMGivenName>{v('prev_spouse_given')}</PMGivenName>
      <TypeOfRelationship>{v('prev_relationship_type')}</TypeOfRelationship>
      <From><FromDate>{v('prev_marriage_from')}</FromDate></From>
      <To><ToDate>{v('prev_marriage_to')}</ToDate></To>
      <PreviouslyMarriedDates><FromYr>{pm_f_yr}</FromYr><FromMM>{pm_f_mm}</FromMM><FromDD>{pm_f_dd}</FromDD><ToYr>{pm_t_yr}</ToYr><ToMM>{pm_t_mm}</ToMM><ToDD>{pm_t_dd}</ToDD></PreviouslyMarriedDates>
      <dob><DOBDay>{pm_dob_dd}</DOBDay><DOBMonth>{pm_dob_mm}</DOBMonth><DOBYear>{pm_dob_yr}</DOBYear></dob>
    </PrevMarriage>
  </MaritalStatus>
  <Languages>
    <nativeLang>{v('native_lang')}</nativeLang>
    <communicateLang>{v('communicate')}</communicateLang>
    <LangTestIndicator>{v('lang_test','N')}</LangTestIndicator>
    <FreqLang/>
  </Languages>
  <Passport>
    <PassportNum>{v('passport_num')}</PassportNum>
    <CountryofIssue>{v('passport_country')}</CountryofIssue>
    <IssueDate>{v('passport_issue')}</IssueDate>
    <ExpiryDate>{v('passport_expiry')}</ExpiryDate>
    <Issue><YYYY>{pi_yr}</YYYY><MM>{pi_mm}</MM><DD>{pi_dd}</DD></Issue>
    <Expiry><YYYY>{pe_yr}</YYYY><MM>{pe_mm}</MM><DD>{pe_dd}</DD></Expiry>
    <TaiwanPIN/><IsraelPassportIndicator/>
  </Passport>
  <natID>
    <SectionHeader xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <q1><natIDIndicator>{v('nat_id_indicator','N')}</natIDIndicator></q1>
    <natIDdocs>
      <DocNum><DocNum>{v('nat_id_num')}</DocNum></DocNum>
      <CountryofIssue><CountryofIssue>{v('nat_id_country')}</CountryofIssue></CountryofIssue>
      <IssueDate><IssueDate>{v('nat_id_issue')}</IssueDate></IssueDate>
      <ExpiryDate>{v('nat_id_expiry')}</ExpiryDate>
    </natIDdocs>
  </natID>
  <USCard>
    <SectionHeader xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <q1><usCardIndicator>{v('us_card_indicator','N')}</usCardIndicator></q1>
    <usCarddocs>
      <DocNum><DocNum>{v('us_card_num')}</DocNum></DocNum>
      <ExpiryDate>{v('us_card_expiry')}</ExpiryDate>
    </usCarddocs>
  </USCard>
  <ContactInformation>
    <AddrLbl xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <Mailing>
      <text xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
      <AddrLine1><POBox/><AptUnit>{v('apt')}</AptUnit><StreetNum>{v('street_num')}</StreetNum><Streetname>{v('street_name')}</Streetname></AddrLine1>
      <AddrLine2><City>{v('city')}</City><Country>{v('country')}</Country><Prov>{v('province')}</Prov><PostalCode>{v('postal_code')}</PostalCode><District/></AddrLine2>
    </Mailing>
    <Resi>
      <SameAsAddr><SameAsMailingInd>{v('same_as_mailing','Y')}</SameAsMailingInd></SameAsAddr>
      <AddrLine1>
        <AptUnit>{v('resi_apt')}</AptUnit>
        <StreetNum>{v('resi_street_num')}</StreetNum>
        <Streetname>{v('resi_street_name')}</Streetname>
      </AddrLine1>
      <AddrLine2>
        <City>{v('resi_city')}</City>
        <Country>{v('resi_country')}</Country>
        <Prov>{v('resi_province')}</Prov>
        <PostalCode>{v('resi_postal_code')}</PostalCode>
        <District/>
      </AddrLine2>
    </Resi>
    <q3-4>
      <Phone>
        <CanOtherInd><CanadaUS>0</CanadaUS><Other>1</Other></CanOtherInd>
        <ActualNumber/><Type>02</Type><NumberExt/>
        <NumberCountry>{v('phone_country_code')}</NumberCountry>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
        <IntlNumber><IntlNumber>{v('phone_number')}</IntlNumber></IntlNumber>
      </Phone>
      <AltPhone>
        <CanOtherInd><CanadaUS>0</CanadaUS><Other>0</Other></CanOtherInd>
        <ActualNumber/><Type/><NumberExt/><NumberCountry/>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
        <IntlNumber><IntlNumber/></IntlNumber>
      </AltPhone>
    </q3-4>
    <q5-6>
      <Fax>
        <CanOtherInd><CanadaUS>0</CanadaUS><Other>0</Other></CanOtherInd>
        <NumberExt/><NumberCountry/><ActualNumber/>
        <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
        <IntlNumber><IntlNumber/></IntlNumber>
      </Fax>
      <Email><Email>{v('email')}</Email></Email>
    </q5-6>
  </ContactInformation>
</Page2>
<Page3>
  <ComingIntoCda>
    <OrigEntry><DateLastEntry>{v('canada_entry_date')}</DateLastEntry><Place>{v('canada_entry_place')}</Place></OrigEntry>
    <PurposeOfVisit><PurposeOfVisit>{v('visit_purpose','04')}</PurposeOfVisit><Other/></PurposeOfVisit>
    <RecentEntry><DateLastEntry/><Place/></RecentEntry>
    <PrevDocNum><docNum>{v('prev_doc_num')}</docNum></PrevDocNum>
  </ComingIntoCda>
  <DetailsOfWork>
    <Purpose><Type>{v('work_permit_type','PGWP')}</Type><Other>{v('work_permit_other')}</Other></Purpose>
    <Employer><Name>{v('employer_name','TBA')}</Name><Addr>{v('employer_address','TBA')}</Addr></Employer>
    <Location><Prov>{v('work_province','06')}</Prov><City>{v('work_city_code','3812')}</City><Addr>{v('work_address','TBA')}</Addr></Location>
    <Occupation><Job>{v('job_title')}</Job><Desc>{v('job_description')}</Desc></Occupation>
    <Duration><FromDate>{v('work_from')}</FromDate><ToDate>{v('work_to')}</ToDate><LMO>{v('lmo_number')}</LMO></Duration>
    <CAQ><CertNum>{v('caq_num')}</CertNum><CertExpiry>{v('caq_expiry')}</CertExpiry></CAQ>
    <ProvNominee><ProvNominee>{v('prov_nominee','N')}</ProvNominee></ProvNominee>
  </DetailsOfWork>
  <Education>
    <EducationIndicator>{v('edu_indicator','Y')}</EducationIndicator>
    <EduLine1>
      <From><YYYY>{edu_yr}</YYYY><MM>{edu_mm}</MM></From>
      <FieldOfStudy>{v('edu_field')}</FieldOfStudy>
      <School>{v('edu_school')}</School>
    </EduLine1>
    <EduLine2>
      <To><YYYY>{edu_tyr}</YYYY><MM>{edu_tmm}</MM></To>
      <City>{v('edu_city')}</City><Country>{v('edu_country')}</Country><Prov>{v('edu_province')}</Prov>
    </EduLine2>
  </Education>
  <Employment>
    <EmpRec1>
      <Line1><From><YYYY>{job_yr}</YYYY><MM>{job_mm}</MM></From><Occupation>{v('occupation')}</Occupation><Employer>{v('employer')}</Employer></Line1>
      <Line2><To><YYYY>{job_tyr}</YYYY><MM>{job_tmm}</MM></To><City>{v('job_city')}</City><Country>{v('job_country')}</Country><ProvState/></Line2>
    </EmpRec1>
  </Employment>
</Page3>
<Page4>
  <EmpRec2>
    <Line1><From><YYYY>{_split_ym(d,'job2_from')[0]}</YYYY><MM>{_split_ym(d,'job2_from')[1]}</MM></From><Occupation>{v('occupation2')}</Occupation><Employer>{v('employer2')}</Employer></Line1>
    <Line2><To><YYYY>{_split_ym(d,'job2_to')[0]}</YYYY><MM>{_split_ym(d,'job2_to')[1]}</MM></To><City>{v('job2_city')}</City><Country>{v('job2_country')}</Country><ProvState/></Line2>
  </EmpRec2>
  <EmpRec3>
    <Line1><From><YYYY>{_split_ym(d,'job3_from')[0]}</YYYY><MM>{_split_ym(d,'job3_from')[1]}</MM></From><Occupation>{v('occupation3')}</Occupation><Employer>{v('employer3')}</Employer></Line1>
    <Line2><To><YYYY>{_split_ym(d,'job3_to')[0]}</YYYY><MM>{_split_ym(d,'job3_to')[1]}</MM></To><City>{v('job3_city')}</City><Country>{v('job3_country')}</Country><ProvState/></Line2>
  </EmpRec3>
  <BackgroundInfo>
    <BackgroundHeader xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <HealthQ><qANY>{v('health_a','N')}</qANY><qBNY>{v('health_b','N')}</qBNY><MedicalDetails>{v('medical_details')}</MedicalDetails><backgroundInfoCalc/></HealthQ>
    <PrevApplied><qANY>{v('prev_applied_a','N')}</qANY><qBNY>{v('prev_applied_b','N')}</qBNY><refusedDetails>{v('refused_details')}</refusedDetails><qCNY>{v('prev_applied_c','N')}</qCNY></PrevApplied>
    <Criminal><qANY>{v('criminal','N')}</qANY><refusedDetails>{v('criminal_details')}</refusedDetails></Criminal>
    <Military><qANY>{v('military','N')}</qANY><militaryServiceDetails>{v('military_details')}</militaryServiceDetails></Military>
    <Occupation><Choice>{v('occupation_choice','N')}</Choice></Occupation>
    <GovPosition><qGovtNY>{v('gov_position','N')}</qGovtNY></GovPosition>
    <Illtreatment><qWitnessNY>{v('illtreatment','N')}</qWitnessNY></Illtreatment>
  </BackgroundInfo>
  <Signature>
    <C1CertificateIssueDate>{today.isoformat()}</C1CertificateIssueDate>
    <TextField2/>
    <FutureComm>{v('future_comm','Y')}</FutureComm>
  </Signature>
</Page4>
</form1>
</xfa:data>
</xfa:datasets>'''


def _idate(date_str):
    """Convert YYYY-MM-DD to 8 <d> digit XML elements (YYYYMMDD)."""
    if date_str and len(date_str) >= 10:
        digits = date_str[:4] + date_str[5:7] + date_str[8:10]
        return ''.join(f'<d>{ch}</d>' for ch in digits)
    return '<d/><d/><d/><d/><d/><d/><d/><d/>'


def build_xml_imm5646(d):
    v = lambda k, default='': _v(d, k, default)

    def parent_xml(p):
        dob = p.get('dob', '')
        return f'''<Parent>
        <parentFamilyName>{p.get('family_name','')}</parentFamilyName>
        <parentGivenNames>{p.get('given_names','')}</parentGivenNames>
        <parentDOB>
          <iDate>{_idate(dob)}</iDate>
          <theDate>{dob}</theDate>
        </parentDOB>
        <parentAddress>{p.get('address','')}</parentAddress>
        <parentTelephone>{p.get('telephone','')}</parentTelephone>
      </Parent>'''

    parents = d.get('parents', [])
    parents_xml = ''.join(parent_xml(p) for p in parents)
    has_parent2 = len(parents) > 1 and parents[1].get('family_name', '')
    today = date.today().isoformat()

    student_dob     = v('student_dob')
    custodian_dob   = v('custodian_dob')
    student_sex     = v('student_sex', '1')   # 1=male, 2=female
    custodian_status = v('custodian_status', '1')  # 1=guardian

    # Page2 declaration fields
    parent1_name = v('parent1_name', parents[0].get('given_names','') + ' ' + parents[0].get('family_name','') if parents else '')
    parent2_name = v('parent2_name', parents[1].get('given_names','') + ' ' + parents[1].get('family_name','') if len(parents) > 1 else '')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<IMM_5646>
<Page1>
  <subStudentInfo>
    <FamilyName>{v('student_family_name')}</FamilyName>
    <GivenNames>{v('student_given_names')}</GivenNames>
    <Citizenship>{v('student_citizenship')}</Citizenship>
    <DOB>
      <iDate>{_idate(student_dob)}</iDate>
      <theDate>{student_dob}</theDate>
    </DOB>
    <schoolAddress>{v('school_address')}</schoolAddress>
    <sex><mfGroup>{student_sex}</mfGroup></sex>
    <studentAddress>{v('student_address')}</studentAddress>
  </subStudentInfo>
  <subParent>
    <Banner xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <Parents>
      {parents_xml}
    </Parents>
  </subParent>
  <subCustodian>
    <FamilyName>{v('custodian_family_name')}</FamilyName>
    <GivenNames>{v('custodian_given_names')}</GivenNames>
    <subStatus><statusGroup>{custodian_status}</statusGroup></subStatus>
    <DOB>
      <iDate>{_idate(custodian_dob)}</iDate>
      <theDate>{custodian_dob}</theDate>
    </DOB>
    <Address>{v('custodian_address')}</Address>
    <Telephone>{v('custodian_telephone')}</Telephone>
  </subCustodian>
  <subDeclaration>
    <nameCustodian>{v('custodian_given_names')} {v('custodian_family_name')}</nameCustodian>
    <nameStudent>{v('student_given_names')} {v('student_family_name')}</nameStudent>
    <swornCity>{v('sworn_city')}</swornCity>
    <swornProv>{v('sworn_prov')}</swornProv>
    <swornCountry>{v('sworn_country')}</swornCountry>
    <swornDay>{v('sworn_day')}</swornDay>
    <swornMonth>{v('sworn_month')}</swornMonth>
    <swornYear>{v('sworn_year')}</swornYear>
    <parentSig1/>
    <subParentSig1date>
      <iDate>{_idate(today)}</iDate>
      <theDate>{today}</theDate>
    </subParentSig1date>
    <notarySig/>
  </subDeclaration>
</Page1>
<Page2>
  <header xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
  <subStudentInfo>
    <FamilyName>{v('student_family_name')}</FamilyName>
    <GivenNames>{v('student_given_names')}</GivenNames>
    <Citizenship>{v('student_citizenship')}</Citizenship>
    <DOB>
      <iDate>{_idate(student_dob)}</iDate>
      <theDate>{student_dob}</theDate>
    </DOB>
    <schoolAddress>{v('school_address')}</schoolAddress>
    <sex><mfGroup>{student_sex}</mfGroup></sex>
    <studentAddress>{v('student_address')}</studentAddress>
  </subStudentInfo>
  <subParent>
    <Banner xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
    <Parents>
      {parents_xml}
    </Parents>
  </subParent>
  <subCustodian>
    <FamilyName>{v('custodian_family_name')}</FamilyName>
    <GivenNames>{v('custodian_given_names')}</GivenNames>
    <subStatus><statusGroup>{custodian_status}</statusGroup></subStatus>
    <DOB>
      <iDate>{_idate(custodian_dob)}</iDate>
      <theDate>{custodian_dob}</theDate>
    </DOB>
    <Address>{v('custodian_address')}</Address>
    <Telephone>{v('custodian_telephone')}</Telephone>
  </subCustodian>
  <subDeclaration>
    <childResideGroup>{v('child_reside_group','1')}</childResideGroup>
    <nameOther>{v('name_other')}</nameOther>
    <nameParent1>{parent1_name}</nameParent1>
    <nameParent2>{parent2_name}</nameParent2>
    <nameStudent>{v('student_given_names')} {v('student_family_name')}</nameStudent>
    <nameCust>{v('custodian_given_names')} {v('custodian_family_name')}</nameCust>
    <parentSig1/>
    <subParentSig1date>
      <iDate>{_idate(today)}</iDate>
      <theDate>{today}</theDate>
    </subParentSig1date>
    <parentSig2/>
    <subParentSig2date>
      <iDate>{_idate(today) if has_parent2 else '<d/><d/><d/><d/><d/><d/><d/><d/>'}</iDate>
      <theDate>{today if has_parent2 else ''}</theDate>
    </subParentSig2date>
    <swornCity>{v('sworn_city')}</swornCity>
    <swornProv>{v('sworn_prov')}</swornProv>
    <swornCountry>{v('sworn_country')}</swornCountry>
    <swornDay>{v('sworn_day')}</swornDay>
    <swornMonth>{v('sworn_month')}</swornMonth>
    <swornYear>{v('sworn_year')}</swornYear>
    <notarySig/>
  </subDeclaration>
  <subPNS xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
</Page2>
</IMM_5646>'''


def build_xml_imm5707(d):
    v = lambda k, default='': _v(d, k, default)
    today = date.today()

    def person_accompanying(val):
        """1=yes, 2=no, empty=unknown"""
        return str(val) if val else ''

    def child_xml(c, include_sig=False):
        acc = person_accompanying(c.get('accompanying', ''))
        sig = '<SectionBsignature/><SectionBdate/>' if include_sig else ''
        return f'''<Child>
      <PaddedEntry>
        {sig}<Accompanying><yesno>{acc}</yesno></Accompanying>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <Relationship>{c.get('relationship','')}</Relationship>
          <FamilyName>{c.get('family_name','')}</FamilyName>
          <GivenNames>{c.get('given_names','')}</GivenNames>
          <DOB>{c.get('dob','')}</DOB>
        </PersonalData>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <COB>{c.get('cob','')}</COB>
          <Address>{c.get('address','')}</Address>
          <MaritalStatus>{c.get('marital_status','')}</MaritalStatus>
          <Occupation>{c.get('occupation','')}</Occupation>
        </PersonalData>
        <buttons xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
      </PaddedEntry>
    </Child>'''

    def empty_child(include_sig=False):
        sig = '<SectionBsignature/><SectionBdate/>' if include_sig else ''
        return f'''<Child>
      <PaddedEntry>
        {sig}<Accompanying><yesno/></Accompanying>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData><Relationship/><FamilyName/><GivenNames/><DOB/></PersonalData>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData><COB/><Address/><MaritalStatus/><Occupation/></PersonalData>
        <buttons xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
      </PaddedEntry>
    </Child>'''

    children = d.get('children', [])
    # 7 child slots total; slots 5,6,7 carry sig fields (matching template)
    children_xml = ''
    for i in range(7):
        if i < len(children):
            children_xml += child_xml(children[i], include_sig=(i >= 4))
        else:
            children_xml += empty_child(include_sig=(i >= 4))

    spouse_acc = person_accompanying(d.get('spouse_accompanying', ''))
    p1_acc = person_accompanying(d.get('parent1_accompanying', '2'))
    p2_acc = person_accompanying(d.get('parent2_accompanying', '2'))

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data>
<IMM_5707>
<page1>
  <Instructions xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
  <SectionA>
    <Applicant>
      <PaddedEntry>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <FamilyName>{v('family_name')}</FamilyName>
          <GivenNames>{v('given_names')}</GivenNames>
          <NativeName>{v('native_name')}</NativeName>
        </PersonalData>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <DOB>{v('dob')}</DOB>
          <COB>{v('cob')}</COB>
          <MaritalStatus>{v('marital_status')}</MaritalStatus>
          <Occupation>{v('occupation')}</Occupation>
        </PersonalData>
        <MarriageInPerson><MarriageInPerson><yesno>{v('marriage_in_person')}</yesno></MarriageInPerson></MarriageInPerson>
      </PaddedEntry>
    </Applicant>
    <Spouse>
      <Relationship xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
      <PaddedEntry>
        <Accompanying><yesno>{spouse_acc}</yesno></Accompanying>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <FamilyName>{v('spouse_family_name')}</FamilyName>
          <GivenNames>{v('spouse_given_names')}</GivenNames>
          <NativeName>{v('spouse_native_name')}</NativeName>
        </PersonalData>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <DOB>{v('spouse_dob')}</DOB>
          <COB>{v('spouse_cob')}</COB>
          <Address>{v('spouse_address')}</Address>
          <MaritalStatus>{v('spouse_marital_status')}</MaritalStatus>
          <Occupation>{v('spouse_occupation')}</Occupation>
        </PersonalData>
        <MarriageInPerson><MarriageInPerson><yesno>{v('spouse_marriage_in_person')}</yesno></MarriageInPerson></MarriageInPerson>
      </PaddedEntry>
    </Spouse>
    <Parent1>
      <PaddedEntry>
        <Accompanying><yesno>{p1_acc}</yesno></Accompanying>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <FamilyName>{v('parent1_family_name')}</FamilyName>
          <GivenNames>{v('parent1_given_names')}</GivenNames>
          <DOB>{v('parent1_dob')}</DOB>
        </PersonalData>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <COB>{v('parent1_cob')}</COB>
          <Address>{v('parent1_address')}</Address>
          <MaritalStatus>{v('parent1_marital_status')}</MaritalStatus>
          <Occupation>{v('parent1_occupation')}</Occupation>
        </PersonalData>
      </PaddedEntry>
    </Parent1>
    <Parent2>
      <PaddedEntry>
        <Accompanying><yesno>{p2_acc}</yesno></Accompanying>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <FamilyName>{v('parent2_family_name')}</FamilyName>
          <GivenNames>{v('parent2_given_names')}</GivenNames>
          <DOB>{v('parent2_dob')}</DOB>
        </PersonalData>
        <Title xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
        <PersonalData>
          <COB>{v('parent2_cob')}</COB>
          <Address>{v('parent2_address')}</Address>
          <MaritalStatus>{v('parent2_marital_status')}</MaritalStatus>
          <Occupation>{v('parent2_occupation')}</Occupation>
        </PersonalData>
      </PaddedEntry>
    </Parent2>
    <PaddedEntry>
      <SectionAsignature/>
      <SectionAdate>{today.isoformat()}</SectionAdate>
    </PaddedEntry>
  </SectionA>
  <SectionB>
    <hideChildren>{0 if children else 1}</hideChildren>
    {children_xml}
    <PaddedEntry><SectionBsignature/><SectionBdate/></PaddedEntry>
  </SectionB>
  <SectionC>
    <SectionCsignature/>
    <SectionCdate>{today.isoformat()}</SectionCdate>
    <infolinksub xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:dataNode="dataGroup"/>
  </SectionC>
</page1>
</IMM_5707>
</xfa:data>
</xfa:datasets>'''


# ── IMM 5713 — AcroForm (PyMuPDF, no Java) ────────────────────────────────────

_5713_PFX = 'IMM_5713[0].page1[0].'


def _5713_field(short):
    return _5713_PFX + short


def _decode_sig(b64_str):
    """Decode base64 signature to PNG bytes.
    Accepts: PNG/JPG (returned as-is), PDF (page 1 → PNG), SVG (→ PNG).
    """
    if not b64_str:
        return None
    try:
        raw = base64.b64decode(b64_str)
    except Exception:
        return None
    if raw[:4] == b'%PDF':
        filetype = 'pdf'
    elif raw[:4] == b'<svg' or raw[:5] == b'<?xml' or b'<svg' in raw[:256]:
        filetype = 'svg'
    else:
        return raw  # PNG / JPG — pass through directly
    try:
        sig_doc = fitz.open(stream=raw, filetype=filetype)
        pix = sig_doc[0].get_pixmap(dpi=150)
        return pix.tobytes('png')
    except Exception:
        return None


def _overlay_sigs_on_pdf(pdf_bytes, placements):
    """Overlay signature images on a PDF.
    placements: list of dicts:
      sig_bytes  — PNG bytes
      anchor     — text to search for on page
      occurrence — which match to use (0=first across all pages)
      dx, dy     — offset from anchor right/top (default 5, -1)
      w          — signature rect width (default 150)
    """
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')

    # Pre-build ordered list of all anchor occurrences across pages
    # keyed by anchor text → list of (page_num, rect) in reading order
    from collections import defaultdict
    anchor_cache = defaultdict(list)
    for pg_num, page in enumerate(doc):
        for anchor in set(p['anchor'] for p in placements):
            for r in page.search_for(anchor):
                anchor_cache[anchor].append((pg_num, r))

    for p in placements:
        sig_bytes = p.get('sig_bytes')
        if not sig_bytes:
            continue
        occ    = p.get('occurrence', 0)
        anchor = p['anchor']
        hits   = anchor_cache.get(anchor, [])
        if occ < 0:
            occ = len(hits) + occ  # support -1 for last, etc.
        if occ < 0 or occ >= len(hits):
            print(f'[sig_overlay] anchor {anchor!r} occurrence {p["occurrence"]} not found (total={len(hits)})')
            continue
        pg_num, anchor_rect = hits[occ]
        dx = p.get('dx', 5)
        dy = p.get('dy', -1)
        w  = p.get('w', 150)
        h  = anchor_rect.height + 2
        sig_rect = fitz.Rect(anchor_rect.x1 + dx, anchor_rect.y0 + dy,
                             anchor_rect.x1 + dx + w, anchor_rect.y0 + dy + h)
        page = doc[pg_num]
        page.insert_image(_sig_left_rect(sig_rect, sig_bytes),
                          stream=sig_bytes, keep_proportion=False)

    buf = io.BytesIO()
    doc.save(buf, deflate=True)
    buf.seek(0)
    return buf.read()


def sig_overlay_imm5645(pdf_bytes, data):
    v = lambda k, default='': _v(data, k, default)
    slots = [
        ('section_a_sig', 0),
        ('section_b_sig', 1),
        ('section_c_sig', 2),
    ]
    placements = []
    for key, occ in slots:
        sig_bytes = _decode_sig(v(key))
        if sig_bytes:
            placements.append({'sig_bytes': sig_bytes, 'anchor': 'Signature', 'occurrence': occ})
    return _overlay_sigs_on_pdf(pdf_bytes, placements)


def sig_overlay_imm5646(pdf_bytes, data):
    v = lambda k, default='': _v(data, k, default)
    # Page1: parentSig1(occ 0), notarySig(occ 1) — notary signs separately, skip
    # Page2: parentSig1(occ 2), parentSig2(occ 3), notarySig(occ 4) — notary signs separately, skip
    slots = [
        ('parent1_sig',  0),
        ('parent1_sig',  2),
        ('parent2_sig',  3),
    ]
    placements = []
    for key, occ in slots:
        sig_bytes = _decode_sig(v(key))
        if sig_bytes:
            placements.append({'sig_bytes': sig_bytes, 'anchor': 'Signature', 'occurrence': occ})
    return _overlay_sigs_on_pdf(pdf_bytes, placements)


def sig_overlay_imm5707(pdf_bytes, data):
    v = lambda k, default='': _v(data, k, default)
    # SectionA: applicant/parent signs (occ 0)
    # SectionB: accompanying adult child signs (occ 1 — first SectionB sig)
    # SectionC: principal applicant signs (occ -1 — always last)
    slots = [
        ('section_a_sig',  0),
        ('section_b_sig',  1),
        ('section_c_sig', -1),
    ]
    placements = []
    for key, occ in slots:
        sig_bytes = _decode_sig(v(key))
        if sig_bytes:
            placements.append({'sig_bytes': sig_bytes, 'anchor': 'Signature', 'occurrence': occ})
    return _overlay_sigs_on_pdf(pdf_bytes, placements)


def _sig_left_rect(field_rect, sig_png_bytes):
    """Left-aligned rect sized to image aspect ratio, capped at field width."""
    try:
        tmp = fitz.open(stream=sig_png_bytes, filetype='png')
        iw, ih = tmp[0].rect.width, tmp[0].rect.height
        tmp.close()
    except Exception:
        iw, ih = 3.0, 1.0
    fh = field_rect.height
    pad = field_rect.width * 0.05
    fw = min(fh * (iw / ih) if ih else fh * 3, field_rect.width - pad)
    return fitz.Rect(field_rect.x0 + pad, field_rect.y0, field_rect.x0 + pad + fw, field_rect.y1)


def build_pdf_imm5713(data):
    v = lambda k, default='': _v(data, k, default)
    today = str(date.today())

    template = os.path.join(PROJECT_ROOT, 'forms', 'imm5713', 'template.pdf')
    doc = fitz.open(template)
    page = doc[0]

    # ── text field values ──────────────────────────────────────────────────────
    field_values = {
        _5713_field('subNo1[0].familyName[0]'):                         v('rep_family_name'),
        _5713_field('subNo1[0].givenName[0]'):                          v('rep_given_name'),
        _5713_field('subNo1[0].subNo2[0].dateBox[0].theDate[0]'):       v('rep_dob'),
        _5713_field('subC[0].dateBox[0].theDate[0]'):                   v('rep_date', today),
    }
    for n in range(1, 6):
        pfx = f'subNo3[0].subRow{n}[0].'
        field_values[_5713_field(pfx + 'TextField1[0]')]    = v(f'member_{n}_name')
        field_values[_5713_field(pfx + 'TextField1[1]')]    = v(f'member_{n}_relationship')
        field_values[_5713_field(pfx + 'DateTimeField1[0]')] = v(f'member_{n}_dob')
        field_values[_5713_field(f'subB[0].subRow{n}[0].DateTimeField1[0]')] = v(f'sig_{n}_date')

    # ── fill text widgets ──────────────────────────────────────────────────────
    sig_b_rects = {}  # n → Rect of the Section B signature placeholder
    for widget in page.widgets():
        name = widget.field_name
        if name in field_values:
            widget.field_value = field_values[name]
            widget.update()
        for n in range(1, 6):
            if name == _5713_field(f'subB[0].subRow{n}[0].TextField1[0]'):
                sig_b_rects[n] = fitz.Rect(widget.rect)

    # ── place Section B signature images ──────────────────────────────────────
    for n in range(1, 6):
        sig_bytes = _decode_sig(v(f'sig_{n}'))
        rect = sig_b_rects.get(n)
        if sig_bytes and rect:
            page.insert_image(_sig_left_rect(rect, sig_bytes), stream=sig_bytes, keep_proportion=False)

    # ── place Section C (rep) signature — no widget, hardcoded position ────────
    rep_sig_bytes = _decode_sig(v('rep_sig'))
    if rep_sig_bytes:
        # "Signature ►" label is at y≈636; date field starts at x≈411
        rep_sig_rect = fitz.Rect(100, 618, 400, 648)
        page.insert_image(_sig_left_rect(rep_sig_rect, rep_sig_bytes), stream=rep_sig_bytes, keep_proportion=False)

    buf = io.BytesIO()
    doc.save(buf, deflate=True)
    buf.seek(0)
    return buf.read()


# ── Form registry ─────────────────────────────────────────────────────────────
FORMS = {
    'imm1294': {
        'build_xml': build_xml_imm1294,
        'required': [
            'family_name', 'given_name', 'sex', 'dob',
            'birth_city', 'birth_country', 'citizenship',
            'cor_country', 'cor_status', 'cor_from', 'marital_status',
            'native_lang', 'communicate',
            'passport_num', 'passport_country', 'passport_issue', 'passport_expiry',
            'street_num', 'street_name', 'city', 'country', 'postal_code',
            'phone_country_code', 'phone_number', 'email',
            'school_name', 'program', 'study_level',
            'school_province', 'school_city', 'school_address',
            'study_from', 'study_to', 'dli',
            'tuition', 'room_board', 'other_costs', 'funds', 'expenses_paid_by',
        ],
    },
    'imm5257': {
        'build_xml': build_xml_imm5257,
        'required': [
            'family_name', 'given_name', 'sex', 'dob',
            'birth_city', 'birth_country', 'citizenship',
            'cor_country', 'cor_status', 'marital_status',
            'native_lang', 'communicate',
            'passport_num', 'passport_country', 'passport_issue', 'passport_expiry',
            'street_name', 'city', 'country',
            'phone_country_code', 'phone_number', 'email',
            'visit_from', 'visit_to', 'funds',
            'canada_contact_name', 'canada_contact_relationship',
        ],
    },
    'imm5645': {
        'build_xml': build_xml_imm5645,
        'sig_overlay': sig_overlay_imm5645,
        'required': [
            'app_name', 'app_dob', 'app_cob', 'app_address', 'app_occupation',
        ],
    },
    'imm1295e': {
        'build_xml': build_xml_imm1295e,
        'required': [
            'family_name', 'given_name', 'sex', 'dob',
            'birth_city', 'birth_country', 'citizenship',
            'cor_country', 'cor_status', 'marital_status',
            'native_lang', 'communicate',
            'passport_num', 'passport_country', 'passport_issue', 'passport_expiry',
            'street_name', 'city', 'country',
            'phone_country_code', 'phone_number', 'email',
            'employer_name', 'employer_address',
            'job_title', 'job_description', 'work_from', 'work_to', 'lmo_number',
        ],
    },
    'imm5646': {
        'build_xml': build_xml_imm5646,
        'sig_overlay': sig_overlay_imm5646,
        'required': [
            'student_family_name', 'student_given_names', 'student_citizenship',
            'student_dob', 'school_address',
            'custodian_family_name', 'custodian_given_names',
            'custodian_dob', 'custodian_address', 'custodian_telephone',
        ],
    },
    'imm5709': {
        'build_xml': build_xml_imm5709,
        'mode': 'validate',
        'required': [
            'family_name', 'given_name', 'sex', 'dob',
            'birth_city', 'birth_country', 'citizenship',
            'cor_country', 'cor_status', 'cor_from', 'cor_to',
            'marital_status', 'native_lang', 'communicate',
            'passport_num', 'passport_country', 'passport_issue', 'passport_expiry',
            'street_name', 'city', 'country', 'province', 'postal_code',
            'phone_number', 'phone_country_code', 'email',
            'canada_entry_date', 'canada_entry_place', 'prev_doc_num',
            'school_name', 'school_province', 'school_city_code', 'school_address',
            'dli', 'study_from', 'study_to',
            'tuition', 'room_board', 'other_costs', 'funds', 'expenses_paid_by',
            'study_program', 'study_level',
        ],
    },
    'imm5707': {
        'build_xml': build_xml_imm5707,
        'sig_overlay': sig_overlay_imm5707,
        'required': [
            'family_name', 'given_names', 'dob', 'cob',
            'marital_status', 'occupation',
        ],
    },
    'imm5710': {
        'build_xml': build_xml_imm5710,
        'mode': 'validate',
        'required': [
            'family_name', 'given_name', 'sex', 'dob',
            'birth_city', 'birth_country', 'citizenship',
            'cor_country', 'cor_status', 'cor_from', 'cor_to',
            'marital_status', 'native_lang', 'communicate',
            'passport_num', 'passport_country', 'passport_issue', 'passport_expiry',
            'street_name', 'city', 'country', 'province', 'postal_code',
            'phone_number', 'phone_country_code', 'email',
            'canada_entry_date', 'canada_entry_place', 'prev_doc_num',
        ],
    },
    'imm5713': {
        'build_pdf': build_pdf_imm5713,
        'required': ['rep_family_name', 'rep_given_name', 'rep_dob'],
    },
}


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get('/health')
def health():
    return jsonify({'status': 'ok'})


@app.get('/forms')
def list_forms():
    result = {}
    for name, form in FORMS.items():
        if 'build_pdf' in form:
            result[name] = {'mode': 'fill', 'engine': 'acroform'}
            continue
        btn = os.path.join(PROJECT_ROOT, 'forms', name, 'button.png')
        mode = form.get('mode') or ('validate' if os.path.exists(btn) else 'fill')
        result[name] = {'mode': mode, 'engine': 'xfa'}
    return jsonify(result)


@app.get('/choices')
def all_choices():
    """Return all extracted select/dropdown choices for all forms."""
    return jsonify(_FORM_CHOICES)


@app.get('/choices/<form_name>')
def form_choices(form_name):
    """Return select/dropdown choices for a specific form."""
    if form_name not in _FORM_CHOICES:
        return jsonify({'error': f'No choices found for form: {form_name}'}), 404
    return jsonify(_FORM_CHOICES[form_name])


@app.get('/choices/<form_name>/<field_name>')
def field_choices(form_name, field_name):
    """Return choices for a specific field in a specific form."""
    form_data = _FORM_CHOICES.get(form_name)
    if not form_data:
        return jsonify({'error': f'No choices found for form: {form_name}'}), 404
    field_data = form_data.get(field_name)
    if not field_data:
        return jsonify({'error': f'No choices found for field: {field_name}'}), 404
    return jsonify(field_data)


@app.post('/generate')
def generate():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    form_name = data.get('form', 'imm1294')
    form = FORMS.get(form_name)
    if not form:
        return jsonify({'error': f'Unknown form: {form_name}', 'available': list(FORMS.keys())}), 400

    fields = data.get('data') or data
    missing = [f for f in form.get('required', []) if not fields.get(f)]
    if missing:
        return jsonify({'error': 'Missing required fields', 'fields': missing}), 400

    # ── AcroForm path (PyMuPDF, no Java) ──────────────────────────────────────
    if 'build_pdf' in form:
        try:
            pdf_bytes = form['build_pdf'](fields)
        except Exception as e:
            return jsonify({'error': f'PDF generation failed: {e}'}), 500
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{form_name}.pdf',
        )

    # ── XFA path (APDFL + Maven) ───────────────────────────────────────────────
    form_dir   = f'forms/{form_name}'
    data_xml   = os.path.join(PROJECT_ROOT, 'forms', form_name, 'data.xml')
    output_dir = os.path.join(PROJECT_ROOT, 'forms', form_name, 'output')
    button_png = os.path.join(PROJECT_ROOT, 'forms', form_name, 'button.png')
    mode = form.get('mode') or ('validate' if os.path.exists(button_png) else 'fill')

    with _lock:
        # 1. Write data.xml
        xml = form['build_xml'](fields)
        os.makedirs(os.path.dirname(data_xml), exist_ok=True)
        with open(data_xml, 'w', encoding='utf-8') as f:
            f.write(xml)

        # 2. Run maven
        print(f'[api] form={form_name} mode={mode}')
        print(f'[api] Running: {MVN} exec:exec -Dexec.mode={mode} -Dform.dir={form_dir}')
        print(f'[api] cwd={PROJECT_ROOT}')
        result = subprocess.run(
            [MVN, 'exec:exec', f'-Dexec.mode={mode}', f'-Dform.dir={form_dir}'],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, encoding='utf-8', errors='replace',
        )
        logs = result.stdout + result.stderr
        APDFL_CRASH = -1073741819
        print(f'[api] Maven exit code: {result.returncode}'
              + (' (known APDFL crash — ignored)' if result.returncode == APDFL_CRASH else ''))
        out = result.stdout
        print(f'[api] Maven stdout (first 3000):\n{out[:3000]}')
        if len(out) > 3000:
            print(f'[api] ... ({len(out) - 3000} chars truncated) ...')
        if result.stderr:
            print(f'[api] Maven stderr:\n{result.stderr[:2000]}')

        # 3. Find output PDF
        os.makedirs(output_dir, exist_ok=True)
        if mode == 'validate':
            pattern = os.path.join(output_dir, 'validate_*.pdf')
        else:
            pattern = os.path.join(output_dir, 'filled_result.pdf')

        matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        print(f'[api] PDF pattern: {pattern}')
        print(f'[api] PDF matches: {matches}')

        if not matches:
            return jsonify({'error': 'PDF not generated', 'logs': logs}), 500

        pdf_path = matches[0]
        print(f'[api] Returning: {pdf_path}')

        if not os.path.exists(pdf_path):
            return jsonify({'error': 'PDF file missing', 'logs': logs}), 500

        # 4. Signature overlay (hybrid: APDFL fill + PyMuPDF signatures)
        # TODO: disabled — confirm government forms accept image-overlaid signatures first
        if False and 'sig_overlay' in form:
            try:
                with open(pdf_path, 'rb') as f:
                    raw = f.read()
                raw = form['sig_overlay'](raw, fields)
                signed_path = pdf_path.replace('.pdf', '_signed.pdf')
                with open(signed_path, 'wb') as f:
                    f.write(raw)
                pdf_path = signed_path
                print(f'[api] Signature overlay applied → {signed_path}')
            except Exception as e:
                print(f'[api] Signature overlay failed (non-fatal): {e}')

        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{form_name}_{os.path.basename(pdf_path)}',
        )


if __name__ == '__main__':
    print(f'[api] Project root : {PROJECT_ROOT}')
    print(f'[api] Maven        : {MVN}')
    print(f'[api] Forms        : {list(FORMS.keys())}')
    print(f'[api] Listening on : http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=False)
