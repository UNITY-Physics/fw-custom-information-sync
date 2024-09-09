import argparse
import os

import flywheel
from files import files_object

SUB_OBJECT = [
    {
        "code": "IVA_202",
        "firstname": "",
        "info": {},
        "label": "IVA_202",
        "lastname": "None",
        "sex": "male",
        "type": "human",
    }
]

SES_IDS = ["gr-_proj-_ses-1.3.12.2.1107.5.2.43.67025.300000190604153707"]

SESSION_OBJECT = [
    {
        "label": id,
    }
    for id in SES_IDS
]

ACQUSITIONS_LABELS = [
    "AAHead_Scout",
    "AAHead_Scout_MPR_cor",
    "AAHead_Scout_MPR_sag",
    "AAHead_Scout_MPR_tra",
    "Design",
    "EvaSeries_GLM",
    "Mean_&_t-Maps",
    "Pedagogy",
    "PhoenixZIPReport",
    "Resting",
    "StartFMRI",
    "Student feedback",
    "Student work",
    "intermediate t-Map",
    "t1_mprage_short",
    "t2w4radiology",
]

ACQUISTIONS_OBJECT = [{"label": a} for a in ACQUSITIONS_LABELS]


def main():
    fw = flywheel.Client()

    project = "BIDS_popup_curation"

    lookup_string = f"{args.group}/{args.project}"

    try:
        fw.lookup(lookup_string)
    except Exception:
        group = fw.get(args.group)
        group.add_project({"label": args.project})

    project = fw.lookup(lookup_string)

    for sub in SUB_OBJECT:
        print(f"subject {sub.get('label')}")
        subject = project.subjects.find(f"label={sub.get('label')}")

        if not subject:
            subject = project.add_subject(sub)
        else:
            subject = subject[0]

        for ses in SESSION_OBJECT:
            print(f"\t session {ses.get('label')}")
            session = subject.sessions.find(f"label={ses.get('label')}")

            if not session:
                session = subject.add_session(ses)
            else:
                session = session[0]

            for acq, acq_file in zip(ACQUISTIONS_OBJECT, files_object):
                print(f"\t\t acquisition {acq.get('label')}")
                acquisition = session.add_acquisition(acq)

                file_name = acq_file["name"]

                if not file_name:
                    file_name = "empty_file.txt"
                    temp_file = open(file_name, "w")
                    temp_file.write("hi")
                    temp_file.close()
                    acquisition.upload_file(file_name)
                    os.remove(file_name)
                    continue

                temp_file = open(file_name, "w")
                temp_file.write("hi")
                temp_file.close()

                acquisition.upload_file(file_name)

                os.remove(file_name)

                acquisition = acquisition.reload()
                f = acquisition.files[0]
                f.update({"modality": acq_file["modality"]})
                f.update_classification(acq_file["classification"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Make a Dummy Project")
    parser.add_argument("--group", help="Group")
    parser.add_argument("--project", help="Project")

    args = parser.parse_args()
    main()
