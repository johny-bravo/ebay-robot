#!/bin/bash
killall ebay_robot.py
yes | rm ebay_robot.py
git pull
chmod 700 ./ebay_robot.py
nohup $python ./ebay_robot.py &
