# forms/

Each subfolder holds one form. The folder name is the `-Dform.dir` value.

## Folder structure

```
forms/<name>/
  template.pdf     ← blank PDF (copy manually, not committed)
  data.xml         ← applicant data to fill in
  button.png       ← screenshot of Validate button (only needed for validate mode)
  output/          ← generated PDFs (auto-created, not committed)
  xfa_fields.xml   ← field dump from discover (not committed)
```

## Forms

| Folder          | Form      | Applicant                         | Mode       |
|-----------------|-----------|-----------------------------------|------------|
| `imm1294`       | IMM 1294  | KOVALENKO Oleksandr (adult, UA)   | validate   |
| `imm5645`       | IMM 5645  | SHARMA Priya (married, IN)        | fill       |
| `imm5646`       | IMM 5646  | NGUYEN Minh Khoa — custodian decl | validate   |

## Commands

```powershell
# Forms without a Validate button — just fill and save
mvn exec:exec "-Dexec.mode=fill" "-Dform.dir=forms/imm5645"

# Forms with a Validate button — fill + open Acrobat + click Validate + save
# Requires button.png screenshot in the form folder
mvn exec:exec "-Dexec.mode=validate" "-Dform.dir=forms/imm1294"

# Discover fields for a new form (run once after adding template.pdf)
mvn exec:exec "-Dexec.mode=discover" "-Dform.dir=forms/<name>"
```

## Adding a new form

```powershell
mkdir forms\<name>
copy <blank>.pdf forms\<name>\template.pdf

# Discover — creates data.xml automatically
mvn exec:exec "-Dexec.mode=discover" "-Dform.dir=forms/<name>"

# Edit data.xml with real values, then:

# If the form has no Validate button:
mvn exec:exec "-Dexec.mode=fill" "-Dform.dir=forms/<name>"

# If the form has a Validate button (barcodes):
# Screenshot the button in Acrobat → forms\<name>\button.png
mvn exec:exec "-Dexec.mode=validate" "-Dform.dir=forms/<name>"
```
