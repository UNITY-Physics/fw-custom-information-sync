# Relabel Container Gear

## Overview

*[Usage](#usage)*

*[FAQ](#faq)*

### Summary

This gear offers a simple way to modify subject, session, and acquisition labels. It was originally created to help make a project compatible with a BIDS project curation template such as reproin.json. Running relabel-container should be done at the project level.  This will generate CSV files that will be populated with a unique list of subject, session and acquisition labels.  These CSV files need to be downloaded and modified to provide new container names. Edited CSV files are then uploaded to the project as an attachment and provided as input to another run of this same gear to modify container names.  This gear can also be run on an individual subject, but cannot be run at the session level.  This gear is not capable of merging subjects or sessions (changing multiple subject or session labels to the same label).

Note: this gear used to be called "bids-pre-curate"

### License 

*License:* MIT

### Classification

*Category:* Analysis

*Gear Level:*

- [X] Project
- [X] Subject
- [ ] Session
- [ ] Acquisition
- [ ] Analysis

----

[[_TOC_]]

----

### Inputs

* *acquisitions*
    - **Type**: File
    - **Optional**: True
    - **Description**: CSV file containing corrected information
* *sessions*
    - **Type**: File
    - **Optional**: True
    - **Description**: CSV file containing corrected session information
* *subjects*
    - **Type**: File
    - **Optional**: True
    - **Description**: CSV file containing corrected subject information

**Note**: These files are created as an output of the initial gear run and then used as an inputs for second run.  At least one of these files must be provided as input for the second run.

### Config

* debug
    - **Type**: boolean
    - **Description**: Log debug messages.
    - **Default**: false
* dry_run
    - **Type**: boolean
    - **Description**: Whether to perform a dry run, logging what would be changed without actually changing it.
    - **Default**: false

### Outputs

#### Files

For initial run (without providing any input files):
- acquisitions.csv
  - Existing unique acquisition labels for the entire project
- sessions.csv
  - Existing unique session labels for the entire project
- subjects.csv
  - Existing unique subject labels for the entire project

For second run (providing input files):
- no outputs are produced.

#### Metadata

No metadata is created or modified by this gear.

### Pre-requisites

This gear is designed to change acquisition labels so that they match what is expected by a project curation template such as reproin.json.  Therefore, the expected labels for anatomical, functional, diffusion acquisitions, etc. need to be known.  Subject and session labels can also be changed if desired.

### Prerequisite Gear Runs

No gears need to be run before this gear but the usual gears for extracting metadata, classification, and dcm2niix will likely be run by gear rules in preparation for running the BIDS curation gear.

## Usage

This gear is run twice.  The first time, it gathers the labels of all subjects, sessions, and acquisitions and returns only the unique strings.  Three csv files are produced as output.  These files need to be edited to add new labels as necessary.  Usually only acquisition labels need to be changed.  

The second run uses the modified csv files to change the labels.  After editing the csv files by adding new labels, the csv files should be attached to the project where they can be used as inputs to the second gear run.  If subject and session labels do not need to be changed, those files to not need to be attached.

## FAQ

[FAQ.md](FAQ.md)

## Contributing

For information about how to develop this gear, see [CONTRIBUTING.md](CONTRIBUTING.md).
<!-- markdownlint-disable-file -->
