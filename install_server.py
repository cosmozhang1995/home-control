#!/usr/bin/env python3

import pip
import subprocess
import os
import sys
import shutil
import json


VERBOSE = False


def run_command(command):
    if isinstance(command, str):
        command = [command]
    if VERBOSE:
        print(" ".join(command))
        return subprocess.run(command).returncode == 0
    else:
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0


def is_apache2_running():
    return run_command(["systemctl", "is-active", "--quiet", "apache2"])


WORK_DIRECTORY = os.path.realpath(os.path.dirname(__file__))
PRIVATE_CONFIG_FILE = os.path.join(WORK_DIRECTORY, "server_config.json")
APACHE_SITE_NAME = "000-home-control"
APACHE_SITE_CONFIG_FILE = f"/etc/apache2/sites-available/{APACHE_SITE_NAME}.conf"


def install():
    # install requirements
    pip.main(['install', 'requests'])

    # check if apache exists
    if not run_command(["a2query", '-a']):
        print("ERROR: Apache2 is not installed")
        exit(1)

    # initialize config file
    if not os.path.exists(PRIVATE_CONFIG_FILE):
        shutil.copy(os.path.join(WORK_DIRECTORY, "server_config.json"), PRIVATE_CONFIG_FILE)
        print("!!! NOTE: please config server_config.json")

    # load private config
    with open(PRIVATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # initialize running directory
    RUNNING_DIRECTORY = config.get('running_directory')
    if not os.path.exists(os.path.join(RUNNING_DIRECTORY)):
        os.makedirs(RUNNING_DIRECTORY)
    if not run_command(["chown", '-R', 'www-data', RUNNING_DIRECTORY]):
        print(f"ERROR: failed to grant www-data with access to {RUNNING_DIRECTORY}")

    # initialize apache site
    APACHE_SITE_NAME = "000-home-control"
    APACHE_SITE_CONFIG_FILE = f"/etc/apache2/sites-available/{APACHE_SITE_NAME}.conf"
    if os.path.exists(APACHE_SITE_CONFIG_FILE):
        print(f"ERROR: site already exists: {APACHE_SITE_CONFIG_FILE}")
        exit(1)
    with open(APACHE_SITE_CONFIG_FILE, 'w') as f:
        f.write(f"""<VirtualHost *:8000>
        ServerName localhost
        DocumentRoot {WORK_DIRECTORY}

        WSGIScriptAlias / {WORK_DIRECTORY}/server.wsgi
        WSGIDaemonProcess home-control user=www-data group=www-data threads=5
        WSGIProcessGroup home-control

        <Directory {WORK_DIRECTORY}>
            Require all granted
        </Directory>
    </VirtualHost>
    """)

    # enable apache site
    if not run_command(["a2ensite", APACHE_SITE_NAME]):
        print("ERROR: failed to enable site")

    # reload apache services
    if is_apache2_running():
        if not run_command(["systemctl", "reload", "apache2"]):
            print("ERROR: failed to restart apache2 services")

    # initialize home-control-socket.service
    SOCKET_SERVICE_NAME = "Home Control Socket"
    SOCKET_SERVICE_FILENAME = "home-control-socket.service"
    SOCKET_SERVICE_FILE = f"/etc/systemd/system/{SOCKET_SERVICE_FILENAME}"
    if os.path.exists(SOCKET_SERVICE_FILE):
        print(f"ERROR: service already exists: {SOCKET_SERVICE_FILE}")
        exit(1)
    with open(SOCKET_SERVICE_FILE, 'w') as f:
        f.write(f"""[Unit]
Description={SOCKET_SERVICE_NAME}
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {WORK_DIRECTORY}/server_socket.py
WorkingDirectory={WORK_DIRECTORY}
Restart=always
RestartSec=3
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
""")
    if not run_command([f"systemctl", "enable", SOCKET_SERVICE_FILENAME]):
        print(f"ERROR: failed to enable service {SOCKET_SERVICE_FILENAME}")
    if not run_command([f"systemctl", "start", SOCKET_SERVICE_FILENAME]):
        print(f"ERROR: failed to start service {SOCKET_SERVICE_FILENAME}")

    print("SUCCESS: installation success!")


def uninstall():
    # load private config
    with open(PRIVATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # remove home-control-socket.service
    SOCKET_SERVICE_NAME = "Home Control Socket"
    SOCKET_SERVICE_FILENAME = "home-control-socket.service"
    SOCKET_SERVICE_FILE = f"/etc/systemd/system/{SOCKET_SERVICE_FILENAME}"
    run_command([f"systemctl", "disable", SOCKET_SERVICE_FILENAME])
    run_command([f"systemctl", "stop", SOCKET_SERVICE_FILENAME])
    try:
        os.remove(SOCKET_SERVICE_FILE)
    except FileNotFoundError:
        pass

    # disable apache site
    run_command(["a2dissite", APACHE_SITE_NAME])

    # remove apache site
    try:
        os.remove(APACHE_SITE_CONFIG_FILE)
    except FileNotFoundError:
        pass

    # reload apache services
    if is_apache2_running():
        if not run_command(["systemctl", "reload", "apache2"]):
            print("ERROR: failed to restart apache2 services")

    # remove running directory
    RUNNING_DIRECTORY = config.get('running_directory', None)
    if RUNNING_DIRECTORY:
        try:
            shutil.rmtree(RUNNING_DIRECTORY)
        except FileNotFoundError:
            pass

    print("SUCCESS: uninstalling success!")


if __name__ == '__main__':
    if '-v' in sys.argv:
        VERBOSE = True
    if '-u' in sys.argv:
        uninstall()
    else:
        install()
