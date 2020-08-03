import socket
import ssl
import ipaddress
import websocket

from urllib.parse import urlparse
from wolfprot import parser


class Socket(parser.Parser):
    ports = {'ssl': 50917, 'no_ssl': 50915, }

    login_level = ('None',
                   'User',
                   'Admin',
                   'Annotation',
                   'Viewer',
                   'App')

    def __init__(self, host: str = '', use_ssl: bool = True, admin_pw: str = 'Password'):
        self.login_dict = dict.fromkeys(self.login_level)
        self.login_dict['Admin'] = admin_pw
        self.host = host
        self.sock = None
        self.ssock = None
        self.port = self.ports['ssl'] if use_ssl is True else self.ports['no_ssl']
        super().__init__()

    def __del__(self):
#        print('delete object')
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

    def login(self, level: str = 'Admin', password=None, admin_pin: int = None):
        '''
        login to cynap
        level = 'None', 'User', 'Admin', 'Annotation', 'Viewer App'

        on success the password for the level will be saved
        if password is 'None' cached password will be used

        return value: None if success else error string.
        '''

        if level in self.login_dict:
            self.login_dict[level] = password
        else:
            raise KeyError(
                f'Login level: {level} -->{self.login_dict.keys()}')

        pw_enc = self.login_dict[level].encode('utf-8').hex()
        pw_len = '{:02x}'.format(len(self.login_dict[level]))
        login_level_val = '{:02x}'.format(int(self.login_level.index(level)))

        to_send = login_level_val + pw_len + pw_enc

        if admin_pin:
            admin_pin_enc = admin_pin.encode('utf-8').hex()
            admin_pin_len = '{:02x}'.format(len(admin_pin))
            to_send += admin_pin_len + admin_pin_enc
        self.send_package('set', 0xcb42, to_send)

        if self.get_error() is None:
            self.login_dict[level] = password

        return self.get_error()

    def admin_logout(self):
        self.send_package('set', 0xcbee, '')
        return self.get_error()

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
#TODO we need a ping pong for websocket
    def __init__(self, uri=None, admin_pw='Password'):
        super().__init__(uri, True, admin_pw)
        u = urlparse(uri)
        if u.scheme != 'wss' and u.scheme != 'ws':
            raise ValueError('not a websocket url')

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
