#!/bin/sh

sudo apt update

cd /home/ubuntu
git clone https://github.com/thomasqueirozb/thunder_demo_tasks.git tasks
cd tasks
sed -i 's/node1/IP_PLACEHOLDER/' portfolio/settings.py
./install.sh
reboot
