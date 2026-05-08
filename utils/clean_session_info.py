
"""Clean legacy metadata by renaming session info variables"""


import logging

import flywheel
import pandas as pd
import csv
from datetime import datetime
import yaml 

log = logging.getLogger(__name__)

def clean_session(ses_dict):

 
    ###. RENAME headers from old template to new template

    with open(f"/flywheel/v0/utils/old_new_harmonization.yaml", 'r') as file:
        metadata = yaml.safe_load(file)

    old_key_new_key = metadata['old_key_new_key']
    delete_keys = metadata['delete_keys']

    with open(f"/flywheel/v0/utils/old_cde_templates.yaml", 'r') as file:
        old_default_template = yaml.safe_load(file)
    
    old_default_template_dict = old_default_template['metadata_template']

    with open(f"/flywheel/v0/utils/cde_template.yaml", 'r') as file:
        defaults = yaml.safe_load(file)

    

    demographics_cde = defaults['Demographics']
    ses_cde = defaults['SES']
    cognitive_cde = defaults['Cognitive']
    defaults_template = demographics_cde | ses_cde | cognitive_cde 

    
    
    for old_key in list(ses_dict.keys()):
        if old_key.startswith('Other'):
            new_key = old_key.replace('Other','other')
            ses_dict[new_key] = ses_dict.pop(old_key)
            updated = True

    for old_key, new_key in old_key_new_key.items():
        if old_key in ses_dict:
            ses_dict[new_key] = ses_dict.get(old_key, None)

            if ses_dict[new_key] == "None" or str(ses_dict[new_key]) == "0" or ses_dict[new_key] == defaults_template.get(new_key): #clean legacy defaults ("0",0,"None" ...)
                
                ses_dict[new_key] = None
            
            ses_dict.pop(old_key, None)
            print('Popping old key...',old_key)
            updated = True
        
        else:
            print(f"No {old_key} found in session.")

    for key in delete_keys + list(old_key_new_key.keys()):
       
        ses_dict.pop(key,None)
        print('Deleting key...',key)

    
    defaults_template.update(old_default_template_dict)
    for key in [key for key in ses_dict if key in defaults_template]:
        
        if ses_dict[key] == defaults_template[key]:
            print(f"Setting {key} to None...")
            ses_dict[key] = None
  
    
    return ses_dict