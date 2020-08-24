import socket
import ssl
import ipaddress
import websocket

from urllib.parse import urlparse
from wolfprot import parser


class Socket(parser.Parser):
    ports = {'ssl': 50917, 'no_ssl': 50915, }

    def __init__(self, host: str = '', use_ssl: bool = True):
        self.host = host
        self.sock = None
        self.ssock = None
        self.port = self.ports['ssl'] if use_ssl is True else self.ports['no_ssl']
        super().__init__()

    def __del__(self):
        self.disconnect()

    def disconnect(self):
        print('disconnect')
        if self.sock:
            self.sock.close()

        if self.ssock:
            self.ssock.close()

    def connect(self):
        ip_addr = str(ipaddress.ip_address(self.host))
        self.disconnect()

        try:
            self.sock = socket.create_connection(
                (ip_addr, self.port), timeout=10)

            if self.port == self.ports['ssl']:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.VerifyFlags.VERIFY_DEFAULT
                self.ssock = context.wrap_socket(
                    self.sock, server_hostname=ip_addr)
                self.ssock.settimeout(10)
            print('connected')
        except socket.timeout as err:
            raise TimeoutError(err)

    def send_receive(self, data):
        try:
            sock = self.ssock if self.port == self.ports['ssl'] else self.sock
            self.reset_buffers()
            sock.send(bytes(data))
            ret = sock.recv(2048)
            self.append_buffer(ret)
            while not self.package_complete() and len(ret) != 0:
                ret = sock.recv(2048)
                self.append_buffer(ret)
            if self.get_error():
                raise ConnectionError(self.get_error())
            return self.get_data()
        except socket.timeout as err:
            raise TimeoutError(err)

    def send_package_ext_len(self, cmd_type='get', cmd=None, data=None):
        rx = self.generate_package(cmd_type, cmd, data, 0, 1)
        return self.send_receive(rx)

    def send_package_ext_hdr(self, cmd_type='get', cmd=None, data=None):
        rx = self.generate_package(cmd_type, cmd, data, 1, 0)
        return self.send_receive(rx)

    def send_package(self, cmd_type='get', cmd=None, data=None):
        rx = self.generate_package(cmd_type, cmd, data, 0, 0)
        return self.send_receive(rx)


class Websocket(Socket):
    # TODO we need a ping pong for websocket
    def __init__(self, uri=None):
        super().__init__(uri, True)
        u = urlparse(uri)
        if u.scheme != 'wss' and u.scheme != 'ws':
            raise ValueError('not a websocket url')

    @classmethod
    def is_websocket_url(cls, uri):
        u = urlparse(uri)
        if u.scheme != 'wss' and u.scheme != 'ws':
            return False
        return True

    def connect(self):
        super().disconnect()
        self.sock = websocket.WebSocket(
            sslopt={'check_hostname': False, 'cert_reqs': ssl.VerifyFlags.VERIFY_DEFAULT})
        self.sock.connect(self.host)
        print('connected')

    def send_receive(self, data):
        try:
            self.reset_buffers()
            self.sock.send_binary(bytes(data))
            ret = self.sock.recv()
            self.append_buffer(ret)
            while not self.package_complete() and len(ret) != 0:
                ret = self.sock.recv()
                self.append_buffer(ret)
            return self.get_data()

        except ValueError as err:
            print("ws tx-rx: error: {0}".format(err))
