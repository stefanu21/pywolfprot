import argparse
from wolfprot import connection
from wolfprot import wolfdoc
from textwrap import dedent


class Cynap:
    def __init__(self, host: str, use_ssl: bool = True, doc_file: str = None, pw: str = 'Password',
                 access_level: str = 'Admin', pin: str = '') -> object:

        if doc_file:
            self.doc = wolfdoc.Wolfdoc(doc_file)
            self.win_types = [(i['comment'], i['value']) for i in self.doc.get_window_types()['values']]
        else:
            self.doc = None
            self.win_types = None

        self.host = host
        self.ssl = use_ssl
        self.pw = pw
        self.access_level = access_level
        self.pin = pin
        self.connection = None

    def connect(self):
        if connection.Websocket.is_websocket_url(self.host):
            self.connection = connection.Websocket(self.host)
        else:
            self.connection = connection.Socket(self.host, self.ssl)
        try:
            self.connection.connect()
            self.login(self.access_level, self.pw, self.pin)

        except (ConnectionRefusedError, TimeoutError) as err:
            print(f'error: {err}')
            return False
        return True

    def send_package(self, section: str, name: str, variant: int = 0, param=None, direction: str = 'GET', return_raw: bool = True) -> dict:
        if self.connection is None:
            return

        data = self.doc.generate_get_request(section, name, variant, param, direction)
        if return_raw:
            return self.raw_package(data)

        return self.doc.generate_get_response(self.raw_package(data), variant)

    def raw_package(self, data: bytearray) -> dict:
        if self.connection is None:
            return

        d = self.connection.send_receive(data)
        h = self.connection.get_header().hex()
        t, cmd, start, stop = self.connection.parse_header()
        e = self.get_error_status()
        res = {'type': t, 'cmd': cmd, 'header': h, 'data': d, 'error': e}
        return res

    def get_error_status(self) -> str:
        if self.connection is None:
            return
        return self.connection.get_error()

    def login(self, access_level: str = 'Admin', password: str = 'Password', admin_pin: str = ''):
        """
        access_level = 'None', 'User', 'Admin', 'Annotation', 'Viewer App'
        """
        login_access_level = {'None': 0x00,
                              'User': 0x01,
                              'Admin': 0x02,
                              'Annotation': 0x03,
                              'Viewer': 0x04,
                              'App': 0x05
                              }

        if access_level not in login_access_level:
            raise KeyError(f'Login level {access_level} not supported: {login_access_level.keys()}')

        param = {'Access level': login_access_level[access_level],
                 'Password length': len(password),
                 'Password': password,
                 'PIN length. This is an optional parameter and is only required if '
                 '<b>Admin Remote PIN</b> is set to <b>PIN required</b> and <b>Access '
                 'level</b> is set to <b>Admin</b>': len(admin_pin),
                 'PIN. This is an optional parameter and is only required if '
                 '<b>Admin Remote PIN</b> is set to <b>PIN required</b> and <b>Access level</b> '
                 'is set to <b>Admin</b>': admin_pin}
        self.send_package('System', 'Login', 0, param, 'SET')


def main():
    """Main program
    """
    description = """Simple programm to send and receive wolfprot commands
    """
    parser = argparse.ArgumentParser(description=dedent(description))
    parser.add_argument('-i',
                        '--IPv4',
                        action='store',
                        dest='host',
                        help='ip address (ipv4)')
    parser.add_argument('-l',
                        '--userlevel',
                        action='store',
                        dest='level',
                        help='"Admin", "User", "None", "Annotation", "Viewer", "App"')
    parser.add_argument('-p',
                        '--password',
                        action='store',
                        dest='pwd',
                        help='password')
    parser.add_argument('-a',
                        '--admin-pin',
                        action='store',
                        dest='pin',
                        help='Admin Pin')
    parser.add_argument('-c',
                        action='store',
                        dest='cmd',
                        help='raw wolfprot command e.g. 09CB020101')
    parser.add_argument('-f',
                        action='store',
                        dest='wp_file',
                        help='wolfprot.json file location')
    args = parser.parse_args()

    cmd = args.cmd
    pwd = args.pwd if args.pwd else 'Password'
    level = args.level if args.level else 'Admin'
    wp_file = args.wp_file if args.wp_file else None
    pin = args.pin if args.pin else ''

    if wp_file is None and args.cmd is None:
        raise BaseException('no wolfprot file or wolfprot command selected')

    cb1 = Cynap(args.host, 1, wp_file, pwd, level, pin)
    print(f'HOST: {args.host}')
    print(f'PW: {pwd}')

    if args.cmd:
        data_ = bytes.fromhex(''.join(''.join(cmd.casefold().split(sep='0x')).split()))
        ret = cb1.raw_package(bytearray(data_))
        print(cb1.doc.get_response(ret))
        return

    while True:
        print('Press q to exit')
        print('SET (0)')
        print('GET (1)')

        d = input(' mode: ')
        direction = 'SET'

        if d == 'q':
            return
        elif d == '1':
            direction = 'GET'

        print('SEARCH CMD(0)')
        print('SEARCH KEYWORD (1)')
        print('SELECT BY CMD (2)')
        print('SELECT BY CATEGORY (3)')

        d = input(' mode: ')
        if d == '0' or d == '2':
            cmd = input('cmd:')
            resp = cb1.doc.get_element_by_cmd(direction, cmd.upper())
            print(resp)
            if resp is None:
                print(' command unknown')
                continue
            elif d == '0':
                print(f' {resp}')
                continue
            else:
                resp = resp.popitem()
                category = resp[0]
                resp = resp[1].popitem()
                sub = resp[0]
        elif d == '1':
            keyword = input('keyword:')
            c = cb1.doc.get_element_by_name(direction, None, None, {'command', })
            print(keyword)
            cat = [(x, y, c[x][y]['command']) for x in c for y in c[x] if
                   x.lower().find(keyword) >= 0 or y.lower().find(keyword) >= 0]
            for i in cat:
                print(i)
            continue
        elif d == '3':
            elements = cb1.doc.get_element_by_name(direction, None, None, {})
            cat_list = list()
            [cat_list.append(i) for i in elements if i not in cat_list]

            for i, k in enumerate(cat_list):
                print(f'{k}: {i}')

            print(f'\n{direction}')
            d = input('category Nr: ')
            if d == 'q':
                return
            category = cat_list[int(d, 10)]
            cat_list = list()
            [cat_list.append(j) for i in elements for j in elements[i] if i == category]
            print(f'\n{category}')
            for i, k in enumerate(cat_list):
                print(f'{k}: {i}')
            print(f'\n{category}')
            d = input('sub-category Nr: ')
            if d == 'q':
                return
            sub = cat_list[int(d, 10)]

        c = cb1.doc.get_element_by_name(direction, category, sub)
        var = c[category][sub]['variations']
        attr = dict()
        var_nr = '0'
        if len(var) > 1:
            var_nr = input(f'variant (max. {len(var) - 1}):')

        i = var[int(var_nr, 10)]
        param = i['request']['parameters']
        for j in param:
            param_id = j.get('parameterID', None)
            if param_id:
                j = cb1.doc.get_param_list(param_id)
            print(f' {j["values"]}')

            param_len = j['length']
            comment = j['comment']
            for a in j['values']:
                print(f' {a["value"]} <- {a["comment"]}')

            i = input(f'{comment}: ')
            if d == 'q':
                return

            if param_len != 0:
                attr[comment] = int(i, 16)
            else:
                attr[comment] = i

        req = cb1.doc.generate_get_request(category, sub, int(var_nr, 10), attr, direction)

        if args.host:
            raw = cb1.raw_package(req)
            err_status = cb1.get_error_status()
            if err_status:
                print(f'error status: {err_status}')
            else:
                print(f'resp: {cb1.doc.generate_get_response(raw, int(var_nr, 10))}')
    return


if __name__ == "__main__":
    main()
