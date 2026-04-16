import json
import subprocess
import requests
import os
import logging
import socket, select
import threading
import re
from collections import namedtuple
import time
from typing import Dict, NamedTuple


RUNNING_DIRECTORY = os.path.join(os.environ.get("LOCALAPPDATA"), "home-control")
if not os.path.exists(RUNNING_DIRECTORY):
    os.makedirs(RUNNING_DIRECTORY)
LOGGING_FILE = os.path.join(RUNNING_DIRECTORY, "pc_client.log")

SOCKET_PORT = 8000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            filename=LOGGING_FILE,
            encoding='utf-8',
            mode='a'
        )
    ]
)


class DnsRecord(NamedTuple):
    hostname: str = ""
    address: str = ""
    timestamp: float = 0

class DnsManager:
    def __init__(self, timeout=0):
        self.dns_map: Dict[str, DnsRecord] = {}
        self.timeout = timeout

    def resolve(self, hostname):
        if hostname in self.dns_map:
            record = self.dns_map[hostname]
            if record.timestamp + self.timeout < time.time():
                del self.dns_map[hostname]
            else:
                return record.address
        try:
            address = socket.gethostbyname(hostname)
        except socket.gaierror:
            return None
        self.dns_map[hostname] = DnsRecord(hostname=hostname, address=address, timestamp=time.time())
        return address

DNS_MANAGER = DnsManager()

class ConfigManager:
    def __init__(self, initial_config={}):
        self._config = initial_config

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, new_config):
        self._config = new_config

    def get(self, key: str, default_value=None):
        key = [k for k in key.split('.') if k]
        c = self._config
        for k in key[:-1]:
            if isinstance(c, dict):
                c = c.get(k, {})
            else:
                return default_value
        return c.get(key[-1], default_value)

CM = ConfigManager()


def compare_config(new_config, key=None, default_value=None):
    # Compare ALL
    if not key:
        if not compare_config(new_config, key="server_base_url"):
            return False
        if not compare_config(new_config, key="pc.launch.display", default_value=1):
            return False
        if not compare_config(new_config, key="pc.launch.uu", default_value=False):
            return False
        if not compare_config(new_config, key="pc.launch.steam", default_value=False):
            return False
        return True

    # Compare a single key
    new_config = ConfigManager(new_config)
    return CM.get(key, default_value) == new_config.get(key, default_value)


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


class RunDaemon:
    def __init__(self):
        self.command = None
        self.stop_flag = False
        self.thread = None
        self.event = threading.Event()

    def start(self):
        if self.thread:
            raise RuntimeError("Daemon is already started")
        logging.error("starting run daemon")
        self.event.clear()
        self.thread = threading.Thread(target=RunDaemon.thread_target, args=(self,))
        self.thread.start()
        logging.error("started run daemon")

    def stop(self):
        logging.error("stopping run daemon")
        self.stop_flag = True
        self.event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join()
        self.thread = None
        logging.error("stopped run daemon")

    def thread_target(self):
        while True:
            self.event.wait()
            self.event.clear()
            if self.stop_flag:
                break
            command = self.command
            self.command = None
            if command is not None:
                self._run_impl(*command)

    def run(self, start_up=True):
        self.command = (start_up,)
        self.event.set()

    def _run_impl(self, start_up=True):
        try:
            logging.info(f"RUNNING with start_up={start_up}")

            pc_config = read_config()

            config = {}
            FETCH_CONFIG_RETRY_COUNT = 10
            FETCH_CONFIG_RETRY_INTERVAL = 1
            SERVER_URL_BASE = pc_config.get('server_base_url')
            if pc_config.get('force_dns_resolve', False):
                match = re.match(r'(\w+)://([\w\.\-]+)(:\d+)?(/.*)?', SERVER_URL_BASE)
                if match is None:
                    logging.error(f"failed to parse server_base_url: {SERVER_URL_BASE}")
                else:
                    SERVER_URL_BASE_HOSTNAME = match.group(2)
                    logging.info(f"DNS resolving {SERVER_URL_BASE_HOSTNAME}")
                    SERVER_URL_BASE_ADDRESS = DNS_MANAGER.resolve(SERVER_URL_BASE_HOSTNAME)
                    if SERVER_URL_BASE_ADDRESS:
                        SERVER_URL_BASE = f"{match.group(1)}://{SERVER_URL_BASE_ADDRESS}{match.group(3) or ''}{match.group(4) or ''}"
                        logging.info(f"DNS resolve {SERVER_URL_BASE_HOSTNAME} success. Using server base url: {SERVER_URL_BASE}")
                    else:
                        logging.info(f"DNS resolve {SERVER_URL_BASE_HOSTNAME} failed")
            for i in range(FETCH_CONFIG_RETRY_COUNT):
                try:
                    CONFIG_URL = f'{SERVER_URL_BASE}/config'
                    logging.info(f"fetching remote config from {CONFIG_URL}")
                    config = requests.get(CONFIG_URL).json()
                    logging.info("fetched remote config:\n" + json.dumps(config, indent=4))
                    break
                except requests.exceptions.RequestException:
                    if i + 1 == FETCH_CONFIG_RETRY_COUNT:
                        logging.info(f"failed to connect socket. no more retry")
                    else:
                        logging.info(f"failed to fetch remote config. retry {i+2} in {FETCH_CONFIG_RETRY_INTERVAL} seconds....")
                    time.sleep(FETCH_CONFIG_RETRY_INTERVAL)
                except KeyboardInterrupt:
                    logging.info("run interrupted by user signal")
                    return
                if self.stop_flag:
                    logging.info("run interrupted by daemon stop")
                    return
            if not config:
                logging.error("failed to fetch remote config. using default config")

            if self.stop_flag:
                logging.info("run interrupted by daemon stop")
                return

            if not start_up:
                if compare_config(config):
                    logging.error("configuration not updated, skip run")
                    return
            
            CM.config = config

            display = CM.get('pc.launch.display', 1)
            if display == 2:
                logging.info("switch to external display")
                set_display("external")
            else:
                logging.info("switch to internal display")
                set_display("internal")
            time.sleep(3)

            if self.stop_flag:
                logging.info("run interrupted by daemon stop")
                return

            if CM.get('pc.launch.uu', False):
                logging.info("launch UU")
                subprocess.Popen(pc_config.get('uu').get('path'))
            if CM.get('pc.launch.steam', False):
                logging.info("launch Steam")
                subprocess.Popen([pc_config.get('steam').get('path'), '-bigpicture'])
        except:
            logging.exception("ERROR:")

RUN_DAEMON = RunDaemon()


KEEP_ALIVE_TIMEOUT = 60*60
KEEP_ALIVE_INTERVAL = 60*10
HEARTBEAT_MSG = b'i_am_pc\n'
BYE_MSG = b'bye\n'

def run_socket_client(max_select_timeout=60):
    try:
        logging.info(f"STARTING socket client")
        pc_config = read_config()
        SERVER_SOCKET_HOST = pc_config.get('server_socket_host')
        SERVER_SOCKET_PORT = pc_config.get('server_socket_port')
        if pc_config.get('force_dns_resolve', False):
            logging.info(f"DNS resolving {SERVER_SOCKET_HOST}")
            SERVER_SOCKET_ADDRESS = DNS_MANAGER.resolve(SERVER_SOCKET_HOST)
            if SERVER_SOCKET_ADDRESS:
                logging.info(f"DNS resolve {SERVER_SOCKET_HOST} success. Using server socket host: {SERVER_SOCKET_ADDRESS}")
                SERVER_SOCKET_HOST = SERVER_SOCKET_ADDRESS
            else:
                logging.info(f"DNS resolve {SERVER_SOCKET_HOST} failed")
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        CONNECT_SOCKET_RETRY_COUNT = 10
        CONNECT_SOCKET_RETRY_INTERVAL = 1
        for i in range(CONNECT_SOCKET_RETRY_COUNT):
            try:
                logging.info(f"connecting socket ({SERVER_SOCKET_HOST}, {SERVER_SOCKET_PORT})")
                client.connect((SERVER_SOCKET_HOST, SERVER_SOCKET_PORT))
                logging.info("server socket connected")
                break
            except OSError:
                if i + 1 == CONNECT_SOCKET_RETRY_COUNT:
                    logging.info(f"failed to connect socket. no more retry")
                else:
                    logging.info(f"failed to connect socket. retry {i+2} in {CONNECT_SOCKET_RETRY_INTERVAL} seconds....")
                time.sleep(CONNECT_SOCKET_RETRY_INTERVAL)
        client.send(HEARTBEAT_MSG)
        logging.info("server socket sent heartbeat message")
        last_heartbeat = time.monotonic()
        last_active = time.monotonic()
        while True:
            now = time.monotonic()
            select_timeout = min(last_heartbeat + KEEP_ALIVE_TIMEOUT - now, max_select_timeout)
            if select_timeout < 0:
                select_timeout = 0.1
            ready, _, _ = select.select([client], [], [], select_timeout)
            if client in ready:
                data = client.recv(1024)
                if not data:
                    logging.error(f"socket client lost connection")
                    break
                data = re.split(r'\s+', data.decode('utf-8'))
                last_active = now
                if 'restart' in data:
                    RUN_DAEMON.run(start_up=False)
            if now - last_active >= KEEP_ALIVE_TIMEOUT:
                logging.error(f"socket client lost heartbeat")
                break
            if now - last_heartbeat >= KEEP_ALIVE_INTERVAL:
                client.send(HEARTBEAT_MSG)
                last_heartbeat = now
                logging.info("server socket sent heartbeat message")
    except KeyboardInterrupt as e:
        logging.info("user interrupt run_socket_client")
        raise e
    finally:
        logging.info(f"closing socket client")
        client.close()

if __name__ == '__main__':
    import sys
    max_select_timeout = 60
    for arg in sys.argv[1:]:
        if arg.startswith('--max-select-timeout='):
            max_select_timeout = int(arg[len('--max-select-timeout='):])
    try:
        RUN_DAEMON.start()
        RUN_DAEMON.run(start_up=True)
        while True:
            try:
                run_socket_client(max_select_timeout=max_select_timeout)
            except KeyboardInterrupt:
                break
            except:
                logging.exception("ERROR:")
    finally:
        RUN_DAEMON.stop()

