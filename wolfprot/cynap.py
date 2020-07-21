import json
import ipaddress
import argparse
from wolfprot import connection
from wolfprot import parser
from textwrap import dedent
from functools import partial
from pathlib import Path


class Cynap:
    def __init__(self, host, use_ssl=True, pw=None, level='Admin', admin_pw='Password', admin_pin=None):
        try:
            self.wv = connection.Websocket(host, admin_pw)
        except:
            self.wv = connection.Socket(host, use_ssl, admin_pw)

        if level == 'Admin':
            self.wv.login(level, admin_pw, admin_pin)
        else:
            self.wv.login(level, pw)

    def raw_package(self, data):
        d = self.wv.send_receive(data)
        h = self.wv.get_header().hex()
        t, cmd, start, stop = self.wv.parse_header()
        e = self.get_error_status()
        return {'type': t, 'cmd': cmd, 'header': h, 'data': d, 'error': e}

    def get_error_status(self):
        return self.wv.get_error()

    def set_firmware_update(self, file):
        p = Path(file)
        if p.exists() is False:
            raise ValueError(f'file: {file} doesn\'t exit')

        self.wv.send_package('set', 0xcb2f, '{:08x}'.format(p.stat().st_size))

        with open(file, 'rb') as f:
            for block in iter(partial(f.read, 128 * 1024), b''):
                self.wv.send_package_ext_hdr('set', 0xcb30, bytearray(block))
                if self.wv.package_complete() is not True or self.wv.get_error() is not None:
                    err = self.wv.get_error()
                    self.wv.send_package('set', 0xcb31)
                    raise ValueError(f'error upload firmware {err}')

        self.wv.send_package('set', 0xcb31)

    def get_preview_pic(self, width, height):
        data = self.wv.send_package('get', 0xcb02, '{:04x}'.format(
            int(width)) + '{:04x}'.format(int(height)) + '0000')
        print(f'error: {self.wv.get_error()}')
        return data[8:]

    def get_save_preview_pic(self, width, height, file):
        with open(file, 'wb') as f:
            p = self.get_preview_pic(width, height)
            f.write(p)


class doc_parser:
    def __init__(self, filename='wolfprot.json'):
        with open(filename) as root:
            self.root = json.load(root)

    def _collect_attr(self, src, attr=None):
        if attr is None:
            return src

        if type(src) == dict:
            d = dict()
            for i in attr:
                d[i] = src[i]
        elif type(src) == list:
            d = list()
            for i in src:
                d.append(self._collect_attr(i, attr))
        else:
            d = src
        return d

    def _collect_rec(self, data, attr=None, deps=0, curr_deps=0, function=None):
        if deps == curr_deps:
            d = self._collect_attr(data, attr)
        else:
            curr_deps += 1
            if type(data) == dict:
                d = dict()
                for i in data:
                    d[i] = self._collect_rec(data[i], attr, deps, curr_deps, self)
            elif type(data) == list:
                d = list()
                for i in data:
                    d.append(self._collect_rec(i, attr, deps, curr_deps, self))
            else:
                d = data
        return d

    def _get_param_list(self, id):
        p = self.root['parameterlist']
        for i in p:
            if i['idx'] == id:
                i['comment'] = i['name']
                return i
        return None

    def get_cmd_obj_by_name(self, categorie=None, name=None, attr=None, get=True):
        t = 'SET' if get is False else 'GET'
        c = self.root[t]['categories']
        if categorie:
            c = c[categorie]

        if categorie is None:
            return self._collect_rec(c, attr, deps=2)

        if name is None:
            return self._collect_rec(c, attr, deps=1)

        return self._collect_attr(c[name], attr)

    def get_cmd_obj_by_cmd(self, cmd, get=True):
        c = self.get_cmd_obj_by_name(None, None, ('command', ), get)
        cat = [(x, y) for x in c for y in c[x] if c[x][y]['command'] == cmd]
        if len(cat):
            item = cat.pop()
            return {'category': item[0], 'sub-category': item[1], 'obj': self.get_cmd_obj_by_name(item[0], item[1], None, get)}
        return None

    def get_request(self, categorie, name, req_param=None, get=True):
        c = self.get_cmd_obj_by_name(categorie, name, None, get)
        var = c['variations']
        cmd = c['command']
        pkg = list()
        for i in var:
            ext_len = None
            ext_hdr = None
            req = i['request']
            paramlenlen = req['parameterLengthLength']
            if paramlenlen == 2:
                ext_len = 1
            elif paramlenlen == 4:
                ext_hdr = 1

            param = req['parameters']
            if(len(param) == 0):
                data = None
            else:
                data = bytes()
                for i in param:
                    val = None
                    id = i.get('parameterID', None)
                    if id:
                        i = self._get_param_list(id)
                    param_len = i['length']
                    comment = i['comment']
                    try:
                        value = req_param[comment]
                    except:
                        print(req_param)
                        print(param)
                        raise

                    if type(value) == int:
                        if param_len == 2:
                            val = bytes.fromhex('{:04x}'.format(value))
                        elif param_len == 1:
                            val = bytes.fromhex('{:02x}'.format(value))
                        elif param_len == 4:
                            val = bytes.fromhex('{:08x}'.format(value))
                        elif param_len == 0:
                            val = bytes(str(value).encode('utf-8'))
                    elif type(value) == str:
                        val = bytes(value.encode('utf-8'))
#                        if len(value) < 0xFF:
#                            val_len = bytes.fromhex('{:02x}'.format(len(value)))
#                        else:
#                            val_len = bytes.fromhex('{:04x}'.format(len(value)))
                    elif type(value) == bytes:
                        val = value
                    else:
                        val = None
                    if val:
                        data += val
            p = parser.Parser()
            t = 'GET' if get is True else 'SET'
            pkg.append(p.generate_package(t, cmd, data, ext_hdr, ext_len))
        return pkg

    def get_response(self, raw_package):
        c = self.get_cmd_obj_by_cmd(raw_package['cmd'].hex().upper(), get=True if raw_package['type'] == 'GET' else False)
        if c is None:
            return None
        category = c['category']
        sub = c['sub-category']
        c = c['obj']

        var = c['variations']
#        cmd = c['command']
#        level = c['userlevel']
        raw = raw_package['data']
        pkg = list()
        for i in var:
            req = i['reply']
            param = req['parameters']
            data = dict()
            if(len(param) != 0):
                n = 0
                prev = None
                for i in param:
                    id = i.get('parameterID', None)
                    if id:
                        i = self._get_param_list(id)
                    param_len = i['length']
                    comment = i['comment']
                    if param_len:
                        data[comment] = int(raw[n:n+param_len].hex(), 16)
                        prev_val = data[comment]
                        n += param_len
                    else:
                        # str_len + str
                        if prev and prev['comment'].find(comment) != -1:
                            # prev_val = string length
                            data[comment] = raw[n:n+prev_val]
                            n += prev_val
                        else:
                            data[comment] = raw
                    prev = i
            pkg.append(data)
        return category, sub, pkg


def main():
    """Main program
    """
    description = """Simple programm to send and receive wolfprot commands
    """
    parser = argparse.ArgumentParser(description=dedent(description))
    parser.add_argument('host',
                        help='ip address (ipv4)')
    parser.add_argument('-l',
                        '--userlevel',
                        action='store',
                        dest='level',
                        help='"Admin", "User", "None", "Annotation", "Viewer", "App"')
    parser.add_argument('-u',
                        '--userlevel-password',
                        action='store',
                        dest='upwd',
                        help='userlevel password')
    parser.add_argument('-a',
                        '--admin-password',
                        action='store',
                        dest='apwd',
                        help='admin password')
    parser.add_argument('-c',
                        action='store',
                        dest='cmd',
                        help='raw wolfprot command e.g. 09CB020101')
    args = parser.parse_args()

    try:
        host_ip = ipaddress.ip_address(args.host)
    except ValueError as err:
        print("error: {0}".format(err))
        return

    cmd = args.cmd
    apwd = args.apwd if args.apwd else 'Password'
    upwd = args.upwd if args.upwd else None
    level = args.level if args.level else 'Admin'

    print(f'IP: {host_ip}')
    print(f'PW: {apwd}')

    try:
        doc = doc_parser()
    except:
        print('doc file not found')
        doc = None

    cb1 = Cynap(host_ip, 1, upwd, level, apwd)

    if args.cmd:
        data_ = bytes.fromhex(''.join(''.join(cmd.casefold().split(sep='0x')).split()))
        ret = cb1.raw_package(bytearray(data_))
        if doc:
            print(doc.get_response(ret))
    else:
        if doc:
            while True:
                print('Press q to exit')
                print('SET (0)')
                print('GET (1)')

                d = input(' mode: ')
                get_cmd = True

                if d == 'q':
                    return
                elif d == '0':
                    get_cmd = False

                print('SEARCH CMD(0)')
                print('SELECT BY CMD (1)')
                print('SELECT BY CATEGORY (2)')
                d = input(' mode: ')
                if d == '0' or d == '1':
                    cmd = input('cmd:')
                    resp = doc.get_cmd_obj_by_cmd(cmd.upper(), get_cmd)
                    if resp is None:
                        print(' command unknown')
                        continue
                    elif d == '0':
                        print(f' {resp}')
                        continue
                    else:
                        category = resp['category']
                        sub = resp['sub-category']
                elif d == '2':
                    cat_list = list()
                    for i, k in enumerate(doc.get_cmd_obj_by_name(None, None, {}, get_cmd)):
                        cat_list.append(k)
                        print(f' {k} ({i})')
                    print('\nGET:') if get_cmd else print('\nSET')
                    d = input('category Nr: ')
                    if d == 'q':
                        return
                    category = cat_list[int(d, 10)]

                    cat_list = list()
                    for i, k in enumerate(doc.get_cmd_obj_by_name(category, None, {}, get_cmd)):
                        cat_list.append(k)
                        print(f' {k} ({i})')
                    print(f'\n{category}')
                    d = input('sub-category Nr: ')
                    if d == 'q':
                        return
                    sub = cat_list[int(d, 10)]

                c = doc.get_cmd_obj_by_name(category, sub, None, get_cmd)
                var = c['variations']
                for i in var:
                    attr = dict()
                    param = i['request']['parameters']
                    for j in param:
                        id = j.get('parameterID', None)
                        if id:
                            j = doc._get_param_list(id)
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

                    print(attr)
                    req = doc.get_request(category, sub, attr, get_cmd)

                    print(req[0].hex())
                    print(doc.get_response(cb1.raw_package(req[0])))
    return


if __name__ == "__main__":
    main()
