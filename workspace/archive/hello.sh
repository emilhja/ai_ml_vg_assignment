#!/bin/bash

HOUR=$(date +%H)

if [ $HOUR -lt 12 ]; then
  echo "Good morning!"
elif [ $HOUR -lt 18 ]; then
  echo "Good afternoon!"
else
  echo "Good evening!"
fi
