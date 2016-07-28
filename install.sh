#!/bin/bash -eux

VENV_DIR=venv
PIP=$VENV_DIR/bin/pip
PIP_PACKAGES="requests pony parse pdfkit pyslack-real python-telegram-bot"

sudo apt install python-pip python-virtualenv
sudo apt-get --reinstall install python-pyasn1 python-pyasn1-modules

# virtualenv with python 2.7.11
# http://mbless.de/blog/2016/01/09/upgrade-to-python-2711-on-ubuntu-1404-lts.html
virtualenv \
    --python=/usr/local/lib/python2.7.11/bin/python \
    --no-site-packages --prompt="(granumsalis)" $VENV_DIR

$PIP install pyasn1
$PIP install $PIP_PACKAGES

#source $VENV_DIR/bin/activate
#deactivate
