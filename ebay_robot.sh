#!/bin/bash
git pull
chmod 700 ./ebay_robot.py
nohup $python ./ebay_robot.py &
