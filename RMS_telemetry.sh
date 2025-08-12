#!/bin/bash

RMSTELEMETRY_PATH=`realpath $0 | xargs dirname`
echo ${RMSTELEMETRY_PATH}

cd ${RMSTELEMETRY_PATH}
python3 RMS_telemetry.py --log-dir=/home/rms/RMS_data/logs/
