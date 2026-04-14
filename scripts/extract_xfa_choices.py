import fitz
import os
import re
import json

forms_dir = r'C:\repos\pdf-xfa\forms'
result = {}


def parse_field_items(content):
    """Parse <field>/<items>/<text> structure from XFA template/form streams."""
    fields = {}
    field_pattern = re.compile(
        r'<field\s+[^>]*name="([^"]+)"[^>]*>(.*?)</field[\s]*>',
        re.DOTALL
    )
    items_pattern = re.compile(r'<items(\s[^>]*)?\s*>(.+?)</items\s*>', re.DOTALL)
    text_pattern = re.compile(r'<text\s*>([^<]*)</text\s*>', re.DOTALL)

    for field_match in field_pattern.finditer(content):
        field_name = field_match.group(1)
        field_body = field_match.group(2)

        all_items = items_pattern.findall(field_body)
        if not all_items:
            continue

        display = []
        saves = []
        for attrs, items_body in all_items:
            texts = [t.strip() for t in text_pattern.findall(items_body) if t.strip()]
            if 'save="1"' in attrs:
                saves.extend(texts)
            else:
                display.extend(texts)

        if display:
            entry = {'display': display}
            if saves:
                entry['values'] = saves
            fields[field_name] = entry

    return fields


def parse_lov_lists(content):
    """Parse <XxxList>/<Xxx lic="..."> LOV structure from xfa:datasets streams."""
    lov = {}
    list_pattern = re.compile(r'<(\w+List)\s*\n?>(.*?)</\1[\s]*>', re.DOTALL)
    item_pattern = re.compile(r'<\w+\s+lic="([^"]*)"\s*\n?>([^<]*)</', re.DOTALL)

    for list_match in list_pattern.finditer(content):
        list_name = list_match.group(1)
        list_body = list_match.group(2)
        items = item_pattern.findall(list_body)
        # Filter blank lic (placeholder empty option) and blank display text
        display = [d.strip() for v, d in items if d.strip()]
        values = [v for v, d in items if d.strip()]
        if display:
            entry = {'display': display}
            if values != display:
                entry['values'] = values
            lov[list_name] = entry

    return lov


def get_all_xfa_streams(pdf_path):
    """Return all XFA-related stream contents from a PDF."""
    doc = fitz.open(pdf_path)
    streams = {}
    for xref in range(1, doc.xref_length()):
        try:
            if doc.xref_is_stream(xref):
                raw = doc.xref_stream(xref)
                if not raw:
                    continue
                # Identify stream type by content markers
                if b'<field ' in raw or b'<items\n>' in raw:
                    streams.setdefault('field_streams', []).append(
                        raw.decode('utf-8', errors='replace')
                    )
                elif b'xfa:datasets' in raw and b'List' in raw and b'lic=' in raw:
                    streams.setdefault('lov_streams', []).append(
                        raw.decode('utf-8', errors='replace')
                    )
        except Exception:
            pass
    doc.close()
    return streams


for form_name in sorted(os.listdir(forms_dir)):
    template_path = os.path.join(forms_dir, form_name, 'template.pdf')
    if not os.path.exists(template_path):
        continue

    try:
        streams = get_all_xfa_streams(template_path)
        if not streams:
            continue

        fields = {}

        # Parse field/items choices from template + form streams
        for content in streams.get('field_streams', []):
            parsed = parse_field_items(content)
            fields.update(parsed)  # later streams override earlier for same name

        # Parse LOV lists from datasets streams
        for content in streams.get('lov_streams', []):
            lov = parse_lov_lists(content)
            # Prefix with 'LOV:' to distinguish from field-level choices
            for list_name, entry in lov.items():
                fields[f'LOV:{list_name}'] = entry

        if fields:
            result[form_name] = fields

    except Exception as e:
        import traceback
        result[form_name] = {'error': str(e), 'traceback': traceback.format_exc()}

with open(r'C:\repos\pdf-xfa\scripts\form_choices.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

# Print summary
for form, fields in result.items():
    if 'error' in fields:
        print(f"{form}: ERROR - {fields['error']}")
    else:
        field_names = list(fields.keys())
        print(f"{form}: {field_names}")
