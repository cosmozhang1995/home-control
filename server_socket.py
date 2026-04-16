import socket
import select
import logging
import time
import os
import json
import re
from typing import Dict, Any, NamedTuple

PRIVATE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "server_config.json")

def read_private_config():
    if os.path.exists(PRIVATE_CONFIG_FILE):
        with open(PRIVATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

RUNNING_DIRECTORY = read_private_config().get('running_directory')
SOCKET_PORT = read_private_config().get('socket_port', 8001)
KEEP_ALIVE_TIMEOUT = 60*60
KEEP_ALIVE_INTERVAL = 60*10
HEARTBEAT_MSG = b'i_am_server\n'
BYE_MSG = b'bye\n'

LOGGING_FILE = os.path.join(RUNNING_DIRECTORY, 'socket.log')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            LOGGING_FILE,
            encoding='utf-8',
            mode='a')
    ]
)

class Client:
    def __init__(self, **kwargs):
        self.addr: str = kwargs.get("addr", "unknown")
        self.last_active: float = kwargs.get("last_active", 0)
        self.last_heartbeat: float = kwargs.get("last_heartbeat", 0)
        self.pc: bool = kwargs.get("pc", False)

clients: Dict[Any, Client] = {}


def remove_client(conn):
    addr = clients.pop(conn, Client()).addr
    try:
        conn.close()
    except OSError:
        pass
    logging.info("Client disconnected: %s  (active: %d)", addr, len(clients))


def restart_pc():
    for conn in clients:
        client = clients[conn]
        if client.pc:
            conn.send(b'restart\n')


def handle_data(conn):
    try:
        data = conn.recv(4096)
    except (ConnectionResetError, OSError):
        data = b""
    if not data:
        remove_client(conn)
        return
    clients[conn].last_active = time.monotonic()
    data = re.split(r'\s+', data.decode('utf-8'))
    logging.debug("Received from %s: %s", clients[conn].addr, data)
    if 'restart' in data:
        logging.info(f"receive restart from {clients[conn].addr}")
        restart_pc()
    if 'i_am_pc' in data:
        logging.info(f"client {clients[conn].addr} set as PC")
        clients[conn].pc = True


def evict_stale_clients(now):
    stale = [c for c, info in clients.items()
             if now - info.last_active > KEEP_ALIVE_TIMEOUT]
    for conn, client in clients.items():
        if now - client.last_active > KEEP_ALIVE_TIMEOUT:
            logging.info("Keep-alive timeout for %s", client.addr)
            remove_client(conn)
        if now - client.last_heartbeat > KEEP_ALIVE_INTERVAL:
            logging.debug("Sending heartbeat to %s", client.addr)
            conn.send(HEARTBEAT_MSG)
            client.last_heartbeat = now


def start_socket_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.setblocking(False)
    server.bind(('', SOCKET_PORT))
    server.listen()
    logging.info("Socket server listening on port %d", SOCKET_PORT)

    try:
        while True:
            readable = [server] + list(clients.keys())
            ready, _, _ = select.select(readable, [], [], 1.0)

            now = time.monotonic()
            for sock in ready:
                if sock is server:
                    conn, addr = server.accept()
                    conn.setblocking(False)
                    clients[conn] = Client(addr=addr, last_active=now, last_heartbeat=now)
                    logging.info("Client connected: %s  (active: %d)", addr, len(clients))
                else:
                    handle_data(sock)

            evict_stale_clients(now)
    except KeyboardInterrupt:
        logging.info("Socket server shutting down by user interruption")
    finally:
        for conn in list(clients):
            remove_client(conn)
        server.close()


if __name__ == "__main__":
    start_socket_server()
