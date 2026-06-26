
"""Clean legacy metadata by renaming session info variables"""


import logging
import yaml

log = logging.getLogger(__name__)

def clean_session(ses_dict):


    ###. RENAME headers from old template to new template

    with open(f"/flywheel/v0/utils/old_new_harmonization.yaml", 'r') as file:
        metadata = yaml.safe_load(file)

    old_key_new_key = metadata['old_key_new_key']
    delete_keys = metadata['delete_keys']

    with open(f"/flywheel/v0/utils/cde_template.yaml", 'r') as file:
        defaults = yaml.safe_load(file)

    demographics_cde = defaults['Demographics']
    ses_cde = defaults['SES']
    cognitive_cde = defaults['Cognitive']
    clinical_cde = defaults.get('Clinical', {})
    derived_cde = defaults.get('Derived', {})
    defaults_template = demographics_cde | ses_cde | cognitive_cde | clinical_cde | derived_cde



    for old_key in list(ses_dict.keys()):
        if old_key.startswith('Other'):
            new_key = old_key.replace('Other','other')
            ses_dict[new_key] = ses_dict.pop(old_key)

    for old_key, new_key in old_key_new_key.items():
        if old_key in ses_dict:
            ses_dict[new_key] = ses_dict.get(old_key, None)

            if ses_dict[new_key] == "None" or ses_dict[new_key] == "0" or ses_dict[new_key] == defaults_template.get(new_key): #clean legacy defaults ("0","None" ...)

                ses_dict[new_key] = None

            ses_dict.pop(old_key, None)
            log.debug('Popping old key... %s', old_key)

        else:
            log.debug("No %s found in session.", old_key)

    for key in delete_keys + list(old_key_new_key.keys()):

        ses_dict.pop(key,None)
        log.debug('Deleting key... %s', key)


    for key in [key for key in ses_dict if key in defaults_template]:

        if ses_dict[key] == defaults_template[key]:
            log.debug("Setting %s to None...", key)
            ses_dict[key] = None


    return ses_dict
