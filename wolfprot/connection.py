import socket
import ssl
import ipaddress
import websocket

from urllib.parse import urlparse
from wolfprot import parser


class Socket(parser.Parser):
    ports = {'ssl': 50917, 'no_ssl': 50915, }

    login_level = {'None': 0, 'User': 1, 'Admin': 2,
                   'Annotation': 3, 'Viewer': 4, 'App': 5, }

    def __init__(self, ip_addr=None, use_ssl=None, admin_pw='Password'):
        self.login_dict = dict.fromkeys(self.login_level.keys(), '')
        self.login_dict['Admin'] = admin_pw
        self.host_ip = None
        self.sock = None
        self.ssock = None
        self.port = None
        super().__init__()
        self.reconnect(ip_addr, use_ssl)

    def __del__(self):
        self.disconnect()

    def disconnect(self):
        if self.sock:
            self.sock.close()

        if self.ssock:
            self.ssock.close()

    def reconnect(self, ip_addr=None, use_ssl=None):

        if ip_addr is None and self.host_ip is None:
            raise ValueError('unknown host')
            return

        print('reconnect')
        self.disconnect()

        if ip_addr:
            self.host_ip = ipaddress.ip_address(ip_addr)

        if use_ssl:
            self.port = self.ports['ssl']
        else:
            self.port = self.ports['no_ssl']

        print(self.port)
        self.sock = socket.create_connection(
            (str(self.host_ip), self.port), timeout=10)

        if self.port == self.ports['ssl']:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.VerifyFlags.VERIFY_DEFAULT
            self.ssock = context.wrap_socket(
                self.sock, server_hostname=str(self.host_ip))
            self.ssock.settimeout(10)
        print('connected')

    def login(self, level, password=None, admin_pin=None):
        '''
        login to cynap
        level = 'None', 'User', 'Admin', 'Annotation', 'Viewer App'

        on success the password for the level will be saved
        if password is 'None' cached password will be used

        return value: None if success else error string.
        '''
        if self.login_dict.get(level) is None:
            raise ValueError(
                f'Login level: {level} -->{self.login_level.keys()}')

        if password is None:
            password = self.login_dict.get(level)

        pw_enc = password.encode('utf-8').hex()
        pw_len = '{:02x}'.format(len(password))
        login_levle_val = '{:02x}'.format(int(self.login_level.get(level)))

        to_send = login_levle_val + pw_len + pw_enc

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

        except ValueError as err:
            print("socket tx-rx: error: {0}".format(err))

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

    def __init__(self, uri=None, admin_pw='Password'):
        self.login_dict = dict.fromkeys(self.login_level.keys(), '')
        self.login_dict['Admin'] = admin_pw
        self.host_ip = None
        self.sock = None
        self.ssock = None
        self.port = None
        super(Socket, self).__init__()
        self.reconnect(uri)

    def reconnect(self, uri=None):

        if uri is None and self.host_ip is None:
            raise ValueError('unknown host')

        if uri:
            self.host_ip = uri

        u = urlparse(uri)

        if u.scheme != 'wss' and u.scheme != 'ws':
            raise ValueError('not a websocket url')

        self.disconnect()
        self.sock = websocket.WebSocket(
            sslopt={'check_hostname': False, 'cert_reqs': ssl.VerifyFlags.VERIFY_DEFAULT})
        self.sock.connect(uri)
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
