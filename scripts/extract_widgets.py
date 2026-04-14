import fitz
import os
import json

forms_dir = r'C:\repos\pdf-xfa\forms'
result = {}

for form_name in sorted(os.listdir(forms_dir)):
    template_path = os.path.join(forms_dir, form_name, 'template.pdf')
    if not os.path.exists(template_path):
        continue
    
    try:
        doc = fitz.open(template_path)
        form_widgets = {}
        for page in doc:
            for w in page.widgets():
                if w.choice_values:
                    form_widgets[w.field_name] = w.choice_values
        if form_widgets:
            result[form_name] = form_widgets
        doc.close()
    except Exception as e:
        result[form_name] = {'error': str(e)}

print(json.dumps(result, indent=2))
