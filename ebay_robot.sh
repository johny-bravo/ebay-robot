#!/bin/bash
yes | rm ebay_robot.py
git pull
chmod 700 ./ebay_robot.py
killall ebay_robot.py
nohup $python ./ebay_robot.py &
