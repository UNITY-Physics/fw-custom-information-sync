#!/usr/bin/env bash 

GEAR=fw-custom-information-sync
IMAGE=flywheel/custom-information-sync:0.0.1
LOG=custom-information-sync-0.0.1-66df097bb7b5b7b4a54f10c4

# Command:
docker run -it --rm --entrypoint bash\
	-v /Users/nbourke/GD/atom/unity/fw-gears/${GEAR}/app/:/flywheel/v0/app\
	-v /Users/nbourke/GD/atom/unity/fw-gears/${GEAR}/run.py:/flywheel/v0/run.py\
	-v /Users/nbourke/GD/atom/unity/fw-gears/${GEAR}/${LOG}/input:/flywheel/v0/input\
	-v /Users/nbourke/GD/atom/unity/fw-gears/${GEAR}/${LOG}/output:/flywheel/v0/output\
	-v /Users/nbourke/GD/atom/unity/fw-gears/${GEAR}/${LOG}/work:/flywheel/v0/work\
	-v /Users/nbourke/GD/atom/unity/fw-gears/${GEAR}/${LOG}/config.json:/flywheel/v0/config.json\
	-v /Users/nbourke/GD/atom/unity/fw-gears/${GEAR}/${LOG}/manifest.json:/flywheel/v0/manifest.json\
	$IMAGE