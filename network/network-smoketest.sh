#!/bin/bash

# enable all output
set -x

# check if lava env
command -v lava-test-case
if [[ $? = "1" ]]; then
  has_lava=False
else
  has_lava=True
fi

# report_result <name> <result> (<measurement> <unit>)
# if result != 0 this is a failure
report_result() {
  name=$1
  result=$2
  if [[ $# = 4 ]]; then
    measurement=$3
    unit=$4
  fi
  echo TestName: $name
  echo TestResult: $result
  echo TestMeasurement: $measurement
  echo TestUnit: $unit
  if [[ -n $measurement ]]; then
    measurement_args="--measurement ${measurement} --units ${unit}"
  else
    measurement_args=""
  fi
  if [[ $has_lava = True ]]; then
    if [[ $result = 0 ]]; then
      lava-test-case $name --result pass $measurement_args
    else
      lava-test-case $name --result fail $measurement_args
    fi
  fi
}

# wait 10 seconds for link up & DHCP
sleep 10

# call ifconfig
ifconfig
report_result ifconfig $?

ping_stdout="$(ping -c 4 -W 1 8.8.8.8)"
ping_ret=$?
# get avg
avg=$(echo "$ping_stdout" | grep avg | grep -Eo '[0-9]+[.][0-9]+' | sed -n '2p')
report_result internet-access $ping_ret $avg ms

ping -c 4 -W 1 www.google.com
report_result dns-access $?
