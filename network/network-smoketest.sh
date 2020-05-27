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

# report_result <name> <result>
# if result != 0 this is a failure
report_result() {
  name=$1
  result=$2
  echo TestName: $name
  echo TestResult: $result
  if [[ $has_lava = True ]]; then
    if [[ $result = 0 ]]; then
      lava-test-case $name --result pass
    else
      lava-test-case $name --result fail
    fi
  fi
}

# call ifconfig
ifconfig
report_result ifconfig $?

ping -c 4 -W 1 8.8.8.8
report_result internet-access $?

ping -c 4 -W 1 www.google.com
report_result dns-access $?