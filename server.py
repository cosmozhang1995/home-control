from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import json
import requests

PORT = 8000
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


def read_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def wrapper_json(func):
    def wrapper(handler: BaseHTTPRequestHandler = None):
        data = None
        content_type = handler.headers.get("Content-Type", "")
        if "application/json" in content_type:
            content_length = int(handler.headers.get("Content-Length", 0))
            raw = handler.rfile.read(content_length)
            if raw:
                data = json.loads(raw)
        resdata = func(data=data)
        if isinstance(resdata, str):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/plain")
            handler.end_headers()
            handler.wfile.write(resdata.encode('utf-8'))
        elif isinstance(resdata, dict):
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps(resdata).encode('utf-8'))
        else:
            handler.send_response(500)
            handler.end_headers()
    return wrapper


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


@wrapper_json
def handler_write_config(data={}, *args, **kwargs):
    if not isinstance(data, dict):
        raise ValueError("Invalid data")
    kwargs = {}
    def flatten_data(rootkey="", data=None):
        if isinstance(data, dict):
            for k in data:
                flatten_data(rootkey + '.' + k, data[k])
        else:
            kwargs[rootkey] = data
    flatten_data(data=data)
    edit_config(**kwargs)
    return "OK"


@wrapper_json
def handler_config(*args, **kwargs):
    config_object = read_config()
    return config_object


@wrapper_json
def handler_delete_config(*args, **kwargs):
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    return "OK"


@wrapper_json
def handler_set_pc_launch_mode(mode="default"):
    if mode == 'default':
        edit_config(
            "pc.launch.steam" = False,
            "pc.launch.uu" = False,
            "display": 1
        )
    elif mode == 'game':
        edit_config(
            "pc.launch.steam" = True,
            "pc.launch.uu" = True,
            "display": 2
        )
    else:
        raise ValueError(f"invalid mode: {mode}")


def handler_notfound(handler: BaseHTTPRequestHandler):
    handler.send_response(404)
    handler.end_headers()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Hello World")
        elif self.path == '/config':
            handler_config(handler=self)
        else:
            handler_notfound(self)
    def do_PUT(self):
        if self.path == "/":
            handler_notfound(self)
        elif self.path == '/config':
            handler_write_config(handler=self)
        else:
            handler_notfound(self)
    def do_DELETE(self):
        if self.path == "/":
            handler_notfound(self)
        elif self.path == '/config':
            handler_delete_config(handler=self)
        else:
            handler_notfound(self)



if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Serving on http://localhost:{PORT}")
    server.serve_forever()
