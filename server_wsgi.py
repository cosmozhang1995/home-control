import os
import json
from urllib.parse import parse_qs
import requests

PRIVATE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "server_config.json")

def read_private_config():
    if os.path.exists(PRIVATE_CONFIG_FILE):
        with open(PRIVATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


RUNNING_DIRECTORY = read_private_config().get('running_directory')
CONFIG_FILE = os.path.join(RUNNING_DIRECTORY, "config.json")


def read_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def edit_config(**kwargs):
    config_object = read_config()
    for key in kwargs:
        keypath = [k for k in key.split('.') if k]
        if len(keypath) == 0:
            continue
        c = config_object
        for step in keypath[:-1]:
            if step not in c:
                c[step] = {}
            c = c[step]
        c[keypath[-1]] = kwargs[key]
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_object, f)


def read_request_json(environ):
    content_type = environ.get("CONTENT_TYPE", "")
    if "application/json" not in content_type:
        return None
    try:
        content_length = int(environ.get("CONTENT_LENGTH", 0))
    except (ValueError, TypeError):
        return None
    if content_length <= 0:
        return None
    raw = environ["wsgi.input"].read(content_length)
    if raw:
        return json.loads(raw)
    return None


def make_response(start_response, data):
    if isinstance(data, str):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [data.encode("utf-8")]
    elif isinstance(data, dict):
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps(data).encode("utf-8")]
    else:
        start_response("500 Internal Server Error", [])
        return [b""]


def response_404(start_response):
    start_response("404 Not Found", [])
    return [b""]


def handle_write_config(environ):
    data = read_request_json(environ)
    if not isinstance(data, dict):
        raise ValueError("Invalid data")
    kv = {}

    def flatten_data(rootkey="", data=None):
        if isinstance(data, dict):
            for k in data:
                flatten_data(rootkey + '.' + k, data[k])
        else:
            kv[rootkey] = data

    flatten_data(data=data)
    edit_config(**kv)
    return "OK"


def handle_config():
    return read_config()


def handle_delete_config():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    return "OK"


def pc_control(value):
    config = read_private_config()
    response = requests.post("https://songguoyun.topwd.top/Esp_Api_new.php",
                            headers={
                                "Content-Type": "application/json"
                            },
                            data=json.dumps({
                                "sgdz_account": config.get("pc").get("sgdz_account"),
                                "sgdz_password": config.get("pc").get("sgdz_password"),
                                "device_name": config.get("pc").get("device_name"),
                                "value": value
                            })).json()
    return response


def pc_startup():
    status_code = int(pc_control(1).get('status', -1))
    if status_code != 0:
        raise SystemError(f"Songguo API returns {status_code}")
def pc_shutdown():
    status_code = int(pc_control(0).get('status', -1))
    if status_code != 0:
        raise SystemError(f"Songguo API returns {status_code}")
def pc_status():
    return pc_control(11)

def handle_pc_launch(mode="default", launch=True):
    if mode == "default":
        edit_config(**{
            "pc.launch.steam": False,
            "pc.launch.uu": False,
            "pc.launch.display": 1,
        })
        if launch:
            pc_startup()
        return "OK"
    elif mode == "game":
        edit_config(**{
            "pc.launch.steam": True,
            "pc.launch.uu": True,
            "pc.launch.display": 2,
        })
        if launch:
            pc_startup()
        return "OK"
    else:
        raise ValueError(f"invalid mode: {mode}")


def handle_pc_shutdown():
    pc_shutdown()
    return "OK"


def application(environ, start_response):
    method = environ["REQUEST_METHOD"]
    path = environ.get("PATH_INFO", "/")

    if method == "GET" and path == "/":
        return make_response(start_response, "Hello World")
    elif method == "GET" and path == "/config":
        return make_response(start_response, handle_config())
    elif method == "PUT" and path == "/config":
        return make_response(start_response, handle_write_config(environ))
    elif method == "DELETE" and path == "/config":
        return make_response(start_response, handle_delete_config())
    elif method == "GET" and path == "/pc_launch":
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        mode = qs.get("mode", ["default"])[0]
        launch = qs.get("launch", ["true"])[0].lower() == "true"
        return make_response(start_response, handle_pc_launch(mode=mode, launch=launch))
    elif method == "GET" and path == "/pc_shutdown":
        return make_response(start_response, handle_pc_shutdown())
    elif method == "GET" and path == "/pc_status":
        return make_response(start_response, pc_status())
    else:
        return response_404(start_response)
