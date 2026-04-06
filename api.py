#!/usr/bin/env python3
"""
Flask REST API — IMM 1294 Study Permit PDF generator.

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
    POST /generate   — generate PDF, returns file download
    GET  /health     — {"status": "ok"}

## Environment variables
    PDF_XFA_ROOT     — project root (default: C:\pdf-xfa)
    API_PORT         — port (default: 5000)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import os
import glob
import subprocess
import threading
from datetime import date

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.environ.get('PDF_XFA_ROOT', r'C:\pdf-xfa')
FORM_DIR     = 'forms/imm1294'
DATA_XML     = os.path.join(PROJECT_ROOT, 'forms', 'imm1294', 'data.xml')
OUTPUT_DIR   = os.path.join(PROJECT_ROOT, 'forms', 'imm1294', 'output')
PORT         = int(os.environ.get('API_PORT', 5000))

# mvn may not be on PATH when run as a service — find it explicitly
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

MVN = os.environ.get('MVN', _find_mvn())

# One request at a time — Acrobat can't run parallel sessions
_lock = threading.Lock()

app = Flask(__name__)
CORS(app)


# ── XML builder ───────────────────────────────────────────────────────────────
def build_xml(d):
    today = date.today()

    def v(key, default=''):
        return str(d.get(key, default))

    def split_date(key):
        val = d.get(key, '')
        if val and len(val) >= 10:
            return val[:4], val[5:7], val[8:10]
        return '', '', ''

    def split_ym(key):
        val = d.get(key, '')
        if val and len(val) >= 7:
            return val[:4], val[5:7]
        return '', ''

    dob_yr,              dob_mm,              dob_dd              = split_date('dob')
    cor_from_yr,         cor_from_mm,         cor_from_dd         = split_date('cor_from')
    passport_issue_yr,   passport_issue_mm,   passport_issue_dd   = split_date('passport_issue')
    passport_expiry_yr,  passport_expiry_mm,  passport_expiry_dd  = split_date('passport_expiry')
    edu_from_yr,         edu_from_mm                              = split_ym('edu_from')
    edu_to_yr,           edu_to_mm                                = split_ym('edu_to')
    job_from_yr,         job_from_mm                              = split_ym('job_from')
    job_to_yr,           job_to_mm                                = split_ym('job_to')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data>
<form1>
<Page1>
  <Header><CRCNum>0</CRCNum></Header>
  <PersonalDetails>
    <ServiceIn><ServiceIn>{v('service_in', '01')}</ServiceIn></ServiceIn>
    <VisaType><VisaType/></VisaType>
    <UCIClientID>{v('uci')}</UCIClientID>
    <Name>
      <FamilyName>{v('family_name')}</FamilyName>
      <GivenName>{v('given_name')}</GivenName>
    </Name>
    <AliasName>
      <AliasFamilyName>{v('alias_family')}</AliasFamilyName>
      <AliasGivenName>{v('alias_given')}</AliasGivenName>
      <AliasNameIndicator><AliasNameIndicator>{v('alias_indicator', '0')}</AliasNameIndicator></AliasNameIndicator>
    </AliasName>
    <Sex><Sex>{v('sex')}</Sex></Sex>
    <DOBYear>{dob_yr}</DOBYear>
    <DOBMonth>{dob_mm}</DOBMonth>
    <DOBDay>{dob_dd}</DOBDay>
    <PlaceBirthCity>{v('birth_city')}</PlaceBirthCity>
    <PlaceBirthCountry>{v('birth_country')}</PlaceBirthCountry>
    <Citizenship><Citizenship>{v('citizenship')}</Citizenship></Citizenship>
    <CurrentCOR>
      <Row2>
        <Country>{v('cor_country')}</Country>
        <Status>{v('cor_status')}</Status>
        <Other/>
        <FromDate>{v('cor_from')}</FromDate>
        <ToDate/>
      </Row2>
    </CurrentCOR>
    <CORDates>
      <FromYr>{cor_from_yr}</FromYr>
      <FromMM>{cor_from_mm}</FromMM>
      <FromDD>{cor_from_dd}</FromDD>
      <ToYr/><ToMM/><ToDD/>
    </CORDates>
    <PCRIndicator>N</PCRIndicator>
    <SameAsCORIndicator>{v('same_as_cor', 'Y')}</SameAsCORIndicator>
    <CountryWhereApplying>
      <Row2><Country/><Status/><Other/><FromDate/><ToDate/></Row2>
    </CountryWhereApplying>
    <CWADates>
      <FromYr/><FromMM/><FromDD/><ToYr/><ToMM/><ToDD/>
    </CWADates>
    <ApplicationValidatedFlag>Yes</ApplicationValidatedFlag>
  </PersonalDetails>
  <MaritalStatus>
    <SectionA>
      <MaritalStatus>{v('marital_status')}</MaritalStatus>
      <DateOfMarriage/>
      <MarriageDate><FromYr/><FromMM/><FromDD/></MarriageDate>
      <FamilyName>{v('spouse_family')}</FamilyName>
      <GivenName>{v('spouse_given')}</GivenName>
    </SectionA>
  </MaritalStatus>
</Page1>

<Page2>
  <MaritalStatus>
    <SectionA>
      <PrevMarriedIndicator>{v('prev_married', 'N')}</PrevMarriedIndicator>
      <DateLastValidated>
        <DateCalc/>
        <Year>{today.year}</Year>
        <Month>{today.month:02d}</Month>
        <Day>{today.day:02d}</Day>
      </DateLastValidated>
      <PMFamilyName/>
      <PrevSpouseDOB>
        <DOBYear/>
        <DOBMonth/>
        <DOBDay/>
      </PrevSpouseDOB>
      <GivenName><PMGivenName/></GivenName>
      <TypeOfRelationship/>
      <FromDate/>
      <ToDate><ToDate/></ToDate>
      <PreviouslyMarriedDates>
        <FromYr/><FromMM/><FromDD/>
        <ToYr/><ToMM/><ToDD/>
      </PreviouslyMarriedDates>
      <Languages>
        <languages>
          <nativeLang><nativeLang>{v('native_lang')}</nativeLang></nativeLang>
          <ableToCommunicate><ableToCommunicate>{v('communicate')}</ableToCommunicate></ableToCommunicate>
          <lov/>
        </languages>
        <LanguageTest>{v('lang_test', '0')}</LanguageTest>
      </Languages>
      <Passport>
        <PassportNum><PassportNum>{v('passport_num')}</PassportNum></PassportNum>
        <CountryofIssue><CountryofIssue>{v('passport_country')}</CountryofIssue></CountryofIssue>
        <IssueDate><IssueDate>{v('passport_issue')}</IssueDate></IssueDate>
        <ExpiryDate>{v('passport_expiry')}</ExpiryDate>
        <IssueYYYY>{passport_issue_yr}</IssueYYYY>
        <IssueMM>{passport_issue_mm}</IssueMM>
        <IssueDD>{passport_issue_dd}</IssueDD>
        <expiryYYYY>{passport_expiry_yr}</expiryYYYY>
        <expiryMM>{passport_expiry_mm}</expiryMM>
        <expiryDD>{passport_expiry_dd}</expiryDD>
        <TaiwanPIN/>
        <IsraelPassportIndicator>0</IsraelPassportIndicator>
      </Passport>
    </SectionA>
  </MaritalStatus>
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
      <Type>Mobile</Type>
      <CanadaUS>0</CanadaUS>
      <Other>1</Other>
      <NumberExt/>
      <NumberCountry>{v('phone_country_code')}</NumberCountry>
      <ActualNumber/>
      <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
      <IntlNumber><IntlNumber>{v('phone_number')}</IntlNumber></IntlNumber>
    </Phone>
    <AltPhone>
      <Type/>
      <CanadaUS>0</CanadaUS>
      <Other>0</Other>
      <NumberExt/>
      <NumberCountry/>
      <ActualNumber/>
      <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
      <IntlNumber><IntlNumber/></IntlNumber>
    </AltPhone>
  </PhoneNumbers>
  <FaxEmail>
    <Phone>
      <CanadaUS>0</CanadaUS>
      <Other>0</Other>
      <NumberExt/>
      <NumberCountry/>
      <ActualNumber/>
      <NANumber><AreaCode/><FirstThree/><LastFive/></NANumber>
      <IntlNumber><IntlNumber/></IntlNumber>
    </Phone>
    <Email>{v('email')}</Email>
  </FaxEmail>
  <DetailsOfStudy>
    <PurposeRow1>
      <schoolName>
        <SchoolName>{v('school_name')}</SchoolName>
        <Program>{v('program')}</Program>
        <Level>{v('study_level')}</Level>
      </schoolName>
      <ProvinceState><Prov>{v('school_province')}</Prov></ProvinceState>
      <CityTown><CityTown>{v('school_city')}</CityTown></CityTown>
      <Address><Address>{v('school_address')}</Address></Address>
      <HowLongStudy>
        <FromDate>{v('study_from')}</FromDate>
        <ToDate>{v('study_to')}</ToDate>
      </HowLongStudy>
      <DLI>{v('dli')}</DLI>
      <StudentNo/>
    </PurposeRow1>
  </DetailsOfStudy>
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
      <FromYear>{edu_from_yr}</FromYear>
      <FromMonth>{edu_from_mm}</FromMonth>
      <ToYear>{edu_to_yr}</ToYear>
      <ToMonth>{edu_to_mm}</ToMonth>
      <FieldOfStudy>{v('edu_field')}</FieldOfStudy>
      <School>{v('edu_school')}</School>
      <CityTown>{v('edu_city')}</CityTown>
      <Country><Country>{v('edu_country')}</Country></Country>
      <ProvState/>
    </Edu_Row1>
  </Education>
  <Occupation>
    <OccupationRow1>
      <FromYear>{job_from_yr}</FromYear>
      <FromMonth>{job_from_mm}</FromMonth>
      <ToYear>{job_to_yr}</ToYear>
      <ToMonth>{job_to_mm}</ToMonth>
      <Occupation><Occupation>{v('occupation')}</Occupation></Occupation>
      <Employer>{v('employer')}</Employer>
      <CityTown><CityTown>{v('job_city')}</CityTown></CityTown>
      <Country><Country>{v('job_country')}</Country></Country>
      <ProvState/>
    </OccupationRow1>
  </Occupation>
</Page3>

<Page4>
  <BackgroundInfo>
    <Choice>N</Choice>
    <Choice>N</Choice>
    <Details><MedicalDetails/></Details>
  </BackgroundInfo>
  <PageWrapper>
    <BackgroundInfo2>
      <VisaChoice1>N</VisaChoice1>
      <VisaChoice2>N</VisaChoice2>
      <Details><refusedDetails/></Details>
      <VisaChoice3>N</VisaChoice3>
    </BackgroundInfo2>
    <BackgroundInfo3><Choice>N</Choice><Details/></BackgroundInfo3>
    <Military><Choice>N</Choice><militaryServiceDetails/></Military>
    <Occupation><Choice>N</Choice></Occupation>
    <GovPosition><Choice>N</Choice></GovPosition>
  </PageWrapper>
  <Consent0><Choice>N</Choice></Consent0>
</Page4>

</form1>
</xfa:data>
</xfa:datasets>'''


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get('/health')
def health():
    return jsonify({'status': 'ok'})


REQUIRED_FIELDS = [
    'family_name', 'given_name', 'sex', 'dob', 'service_in',
    'birth_city', 'birth_country', 'citizenship',
    'cor_country', 'cor_status', 'cor_from',
    'marital_status',
    'native_lang', 'communicate',
    'passport_num', 'passport_country', 'passport_issue', 'passport_expiry',
    'street_num', 'street_name', 'city', 'country', 'postal_code',
    'phone_country_code', 'phone_number', 'email',
    'school_name', 'program', 'study_level',
    'school_province', 'school_city', 'school_address',
    'study_from', 'study_to', 'dli',
    'tuition', 'room_board', 'other_costs', 'funds', 'expenses_paid_by',
]


@app.post('/generate')
def generate():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        return jsonify({'error': 'Missing required fields', 'fields': missing}), 400

    with _lock:
        # 1. Write data.xml
        xml = build_xml(data)
        os.makedirs(os.path.dirname(DATA_XML), exist_ok=True)
        with open(DATA_XML, 'w', encoding='utf-8') as f:
            f.write(xml)

        # 2. Run maven
        print(f'[api] Running: {MVN} exec:exec -Dexec.mode=validate -Dform.dir={FORM_DIR}')
        print(f'[api] cwd: {PROJECT_ROOT}')
        result = subprocess.run(
            [MVN, 'exec:exec', '-Dexec.mode=validate', f'-Dform.dir={FORM_DIR}'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        logs = result.stdout + result.stderr
        APDFL_CRASH = -1073741819
        print(f'[api] Maven exit code: {result.returncode}'
              + (' (known APDFL native crash — ignored)' if result.returncode == APDFL_CRASH else ''))
        # Print first 3000 chars — that's where Java/Python output is; end is just stack trace
        out = result.stdout
        print(f'[api] Maven stdout (first 3000):\n{out[:3000]}')
        if len(out) > 3000:
            print(f'[api] ... ({len(out) - 3000} chars truncated) ...')
        if result.stderr:
            print(f'[api] Maven stderr:\n{result.stderr[:2000]}')

        # 3. Find the output PDF (newest validate_result_*.pdf)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        pattern = os.path.join(OUTPUT_DIR, 'validate_result*.pdf')
        matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        print(f'[api] PDF search pattern: {pattern}')
        print(f'[api] PDF matches: {matches}')

        if not matches:
            return jsonify({'error': 'PDF not generated', 'logs': logs}), 500

        pdf_path = matches[0]
        print(f'[api] Returning PDF: {pdf_path}')

        if not os.path.exists(pdf_path):
            return jsonify({'error': 'PDF file missing after generation', 'logs': logs}), 500

        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=os.path.basename(pdf_path),
        )


if __name__ == '__main__':
    print(f'[api] Project root : {PROJECT_ROOT}')
    print(f'[api] Data XML     : {DATA_XML}')
    print(f'[api] Output dir   : {OUTPUT_DIR}')
    print(f'[api] Listening on : http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=False)
