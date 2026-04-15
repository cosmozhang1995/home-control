import json
import subprocess
import requests
import os
import logging

RUNNING_DIRECTORY = os.path.join(os.environ.get("LOCALAPPDATA"), "home-control")
if not os.path.exists(RUNNING_DIRECTORY):
    os.makedirs(RUNNING_DIRECTORY)
LOGGING_FILE = os.path.join(RUNNING_DIRECTORY, "pc_client.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    encoding="utf-8",
    filename=LOGGING_FILE,
    filemode="a"
)

try:
    CONFIG_FILE = os.path.join(os.path.dirname(__file__), "pc_config.json")

    def set_display(mode="internal"):
        result = subprocess.run(["DisplaySwitch", f"/{mode}"])
        if result.returncode != 0:
            raise RuntimeError(f"DisplaySwitch failed with return code {result.returncode}")

    def read_config():
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}

    pc_config = read_config()

    config = {}
    FETCH_CONFIG_RETRY_COUNT = 10
    FETCH_CONFIG_RETRY_INTERVAL = 1
    SERVER_URL_BASE = pc_config.get('server_base_url')
    for i in range(FETCH_CONFIG_RETRY_COUNT):
        try:
            CONFIG_URL = f'{SERVER_URL_BASE}/config'
            logging.info(f"fetching remote config from {CONFIG_URL}")
            config = requests.get(CONFIG_URL).json()
            logging.info("fetched remote config:\n" + json.dumps(config, indent=4))
        except requests.exceptions.RequestException:
            logging.info(f"failed to fetch remote config. retry {i+2} in {FETCH_CONFIG_RETRY_INTERVAL} seconds....")
            import time
            time.sleep(FETCH_CONFIG_RETRY_INTERVAL)
    if not config:
        logging.error("failed to fetch remote config. using default config")

    display = config.get('pc', {}).get('launch', {}).get('display', 1)
    if display == 2:
        logging.info("switch to external display")
        set_display("external")
    else:
        logging.info("switch to internal display")
        set_display("internal")

    launch = config.get('pc', {}).get('launch', {})
    if launch.get('uu', False):
        logging.info("launch UU")
        subprocess.Popen(pc_config.get('uu').get('path'))
    if launch.get('steam', False):
        logging.info("launch Steam")
        subprocess.Popen([pc_config.get('steam').get('path'), '-bigpicture'])
except:
    logging.exception("ERROR:")
