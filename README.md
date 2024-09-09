# Custom Information Sync Gear

## Overview

*[Usage](#usage)*

*[FAQ](#faq)*

### Summary

This gear offers a simple way to modify custom information in session containers. Running custom-information-sync should be done at the project level. This will generate a CSV file that will be populated with a unique list of subject, session labels and existing custom information.  This CSV file needs to be downloaded and modified to provide new custom information. Edited CSV files are then uploaded to the project as an attachment and provided as input to another run of this same gear to modify custom information. 
*This gear is not capable of merging subjects or sessions (changing multiple subject or session labels to the same label). Edits to subject or session labels should be done manually in Flywheel.*


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

* *sessions*
    - **Type**: File
    - **Optional**: True
    - **Description**: CSV file containing custom session information

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
- <project>.csv
  - Existing unique subject & session labels for the entire project with custom session information.

For second run (providing input files):
- no outputs are produced.

#### Metadata

No metadata is created or modified by this gear.

### Pre-requisites

This gear is designed to add/change custom information in session containers.  It is typically used to fill in relevant information to accompany imaging data.  For example, it can be used to capture birth_weight, birth_ga, offline QC or other information that can be used for normative modeling or global health analysis.  

### Prerequisite Gear Runs

No gears need to be run before this gear but the usual gears for extracting metadata, classification, and dcm2niix will likely be run by gear rules in preparation for running the BIDS curation gear.

## Usage

This gear is run twice.  The first time, it gathers the labels of all subjects, sessions, and returns only the unique strings.  A project csv file is produced as output.  This file needs to be edited to add new custom information as necessary. Usually only pre-specified headers need to have values added.  

The second run uses the modified csv file to update the sesson information container.  After editing the csv file by adding new information, the csv file should be attached to the project where they can be used as inputs to the second gear run.  *If subject and session labels are changed, this new information will not be synced.*

## FAQ

[FAQ.md](FAQ.md)

## Contributing

For information about how to develop this gear, see [CONTRIBUTING.md](CONTRIBUTING.md).
<!-- markdownlint-disable-file -->
# fw-custom-information-sync
