import json
import ipaddress
import argparse
from wolfprot import connection
from wolfprot import parser
from textwrap import dedent
from functools import partial
from pathlib import Path


class Cynap:
    def __init__(self, host: str, use_ssl: bool = True, pw: str = None, level: str = 'Admin',
                 admin_pw: str = 'Password', admin_pin: int = None) -> object:
        try:
            self.wv = connection.Websocket(host, admin_pw)

        except (ValueError, TimeoutError) as err:
            self.wv = connection.Socket(host, use_ssl, admin_pw)

        self.wv.connect()

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
        return data[8:]

    def get_save_preview_pic(self, width, height, file):
        with open(file, 'wb') as f:
            p = self.get_preview_pic(width, height)
            f.write(p)


class doc_parser:
    def __init__(self, filename=None):
        if filename is None:
            filename = 'wolfprot.json'
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

    def _get_param_list(self, value=None):
        p = self.root['parameterlist']
        attr = 'idx' if type(value) is int else 'name'
        for i in p:
            if i[attr] == value:
                i['comment'] = i['name']
                return i
        return None

    def get_window_types(self):
        return self._get_param_list('Window type')

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
        c = self.get_cmd_obj_by_name(None, None, ('command',), get)
        cat = [(x, y) for x in c for y in c[x] if c[x][y]['command'] == cmd]
        if len(cat):
            item = cat.pop()
            return {'category': item[0], 'sub-category': item[1],
                    'obj': self.get_cmd_obj_by_name(item[0], item[1], None, get)}
        return None

    def get_request(self, categorie, name, variant=0, req_param=None, get=True):
        """

        Returns
        -------
        object
        """
        c = self.get_cmd_obj_by_name(categorie, name, None, get)
        var = c['variations']
        cmd = c['command']
        pkg = list()
        if len(var) <= variant:
            raise ValueError('variant out of range')
        else:
            i = var[variant]
            ext_len = None
            ext_hdr = None
            req = i['request']
            paramlenlen = req['parameterLengthLength']
            if paramlenlen == 2:
                ext_len = 1
            elif paramlenlen == 4:
                ext_hdr = 1

            param = req['parameters']
            if len(param) == 0:
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

    def get_response(self, raw_package, variant=0):
        c = self.get_cmd_obj_by_cmd(raw_package['cmd'].hex().upper(),
                                    get=True if raw_package['type'] == 'GET' else False)
        if c is None:
            return None
        category = c['category']
        sub = c['sub-category']
        c = c['obj']

        var = c['variations']
        cmd = c['command']
#        level = c['userlevel']
        raw = raw_package['data']
        pkg = list()
#        print(f'resp raw: {raw}')
        if len(var) > variant:
            i = var[variant]

            req = i['reply']
            param = req['parameters']

            if len(param) != 0:
                start = 0
                end = 0

                rm_param = list()
                data_common = dict()
                if cmd == 'CBBA':  # Window 2 command
                    f = ('Window reference width', 'Window reference height')
                    rm_param = [i for i in param if i['comment'] in f]
                    print(raw[start:])

                for i in rm_param:
                    param_len = i['length']
                    comment = i['comment']
                    if param_len:
                        end = start + param_len
                        data_common[comment] = int(raw[start:end].hex(), 16)
#                        print(f'{comment}: {data_common[comment]}')
                        prev_val = data_common[comment]
                        start = end

                if len(data_common):
                    pkg.append(data_common)

                # I expect it is a repeating block when the raw package
                # size is not finish after first iteration over the parameters
                while end < len(raw):
#                    print(f'end: {end}, rawlen: {len(raw)}')
                    prev = None
                    data = dict()
                    for i in param:

                        if i in rm_param:
                            continue

                        if start >= len(raw):
                            # add string value when previous value was the length value with data value zero
                            if prev and prev['comment'].find(comment) != -1 and prev_val == 0:
                                comment = i['comment']
                                data[comment] = bytearray()
                            break
                        param_id = i.get('parameterID', None)
                        if param_id:
                            i = self._get_param_list(param_id)
                        param_len = i['length']
                        comment = i['comment']
                        if param_len:
                            end = start + param_len
                            data[comment] = int(raw[start:end].hex(), 16)
                            prev_val = data[comment]
#                            print(f'1:{comment}: {prev_val} len: {param_len}')
                            start = end
                        else:
                            # str_len + str
                            if prev and prev['comment'].find(comment) != -1:
                                # prev_val = string length
                                end = start + prev_val
#                                print(f'start: {start}, end: {end}')
                                data[comment] = raw[start:end]
#                                print(f'prev: {prev["comment"]}: {prev_val}')
#                                print(f'2:{comment}: {data[comment]} len: {param_len}')
                                start = end
                            else:
                                data[comment] = raw
#                                print(f'3:{comment}: {data[comment]} len: {param_len}')
                                end = len(raw)
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
    parser.add_argument('-f',
                        action='store',
                        dest='wp_file',
                        help='wolfprot.json file location')
    args = parser.parse_args()

    cmd = args.cmd
    apwd = args.apwd if args.apwd else 'Password'
    upwd = args.upwd if args.upwd else None
    level = args.level if args.level else 'Admin'
    wp_file = args.wp_file if args.wp_file else None

    try:
        doc = doc_parser(wp_file)
    except:
        print(f'doc file {wp_file} not found')
        doc = None

    if doc is None and args.cmd is None:
        return

    cb1 = Cynap(args.host, 1, upwd, level, apwd)
    print(f'HOST: {args.host}')
    print(f'PW: {apwd}')

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
                print('SEARCH KEYWORD (1)')
                print('SELECT BY CMD (2)')
                print('SELECT BY CATEGORY (3)')

                d = input(' mode: ')
                if d == '0' or d == '2':
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
                elif d == '1':
                    keyword = input('keyword:')
                    c = doc.get_cmd_obj_by_name(None, None, {'command', }, get_cmd)
                    print(keyword)
                    cat = [(x, y, c[x][y]['command']) for x in c for y in c[x] if
                           x.lower().find(keyword) >= 0 or y.lower().find(keyword) >= 0]
                    for i in cat:
                        print(i)
                    continue
                elif d == '3':
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
                attr = dict()
                var_nr = '0'
                if len(var) > 1:
                    var_nr = input(f'variant (max. {len(var) - 1}):')

                i = var[int(var_nr, 10)]
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
                req = doc.get_request(category, sub, int(var_nr, 10), attr, get_cmd)
                print(req[0].hex())
                raw = cb1.raw_package(req[0])
                err_status = cb1.get_error_status()
                if err_status:
                    print(f'error status: {err_status}')
                else:
                    print(f'resp: {doc.get_response(cb1.raw_package(req[0]), int(var_nr, 10))}')
    return


if __name__ == "__main__":
    main()
