
"""Clean legacy metadata by renaming session info variables"""


import logging
import yaml

log = logging.getLogger(__name__)

def clean_session(ses_dict, harmonization_map=None, defaults_template=None):
    """Rename legacy session keys and remove obsolete ones.

    harmonization_map and defaults_template should be pre-loaded by the caller
    and passed in. The None-fallback paths open files at /flywheel/v0/utils/
    which only exist inside the gear container and will raise FileNotFoundError
    in any other environment (tests, local scripts).
    """

    ###. RENAME headers from old template to new template

    if harmonization_map is None:
        with open(f"/flywheel/v0/utils/old_new_harmonization.yaml", 'r') as file:
            harmonization_map = yaml.safe_load(file)

    old_key_new_key = harmonization_map['old_key_new_key']
    delete_keys = harmonization_map['delete_keys']

    if defaults_template is None:
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

            if ses_dict[new_key] == "None" or ses_dict[new_key] == "0":  # clear legacy string placeholders only

                ses_dict[new_key] = None

            ses_dict.pop(old_key, None)
            log.debug('Popping old key... %s', old_key)

        else:
            log.debug("No %s found in session.", old_key)

    for key in delete_keys + list(old_key_new_key.keys()):

        ses_dict.pop(key,None)
        log.debug('Deleting key... %s', key)

    return ses_dict
