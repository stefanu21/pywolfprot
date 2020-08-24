import json
import time
from wolfprot import parser as wp_parser


class Wolfdoc():
    main_parameters = ['publicName', 'timestamp', 'commandLength', 'command', 'userlevel', 'variations']
    package_types = ['request', 'reply']
    direction_types = ['GET', 'SET']
    edit_actions = ['rename', 'add', 'remove']

    def __init__(self, file):
        self.file = file
        self.element = None
        self.parameter = None

        with open(file) as fp:
            self.root = json.load(fp)

        self.supported_devices = self.root['devices']
        self.userleves = self.root['userlevels']
        self.param_list = self.root['parameterlist']

    def dump_json(self, file=None):
        if file is None:
            file = self.file

        with open(file, 'w', newline='\n') as fp:
            json.dump(self.root, fp, indent=2)

    def get_window_types(self):
        return self.get_param_list('Window type')

    def generate_get_request(self, section: str, name: str, variant: int = 0, req_param=None, direction: str = 'GET'):
        c = self.get_element_by_name(direction, section, name, {'command', 'variations'})
        cmd = c[section][name]['command']
        var = c[section][name]['variations']

        if len(var) <= variant:
            raise ValueError('variant out of range')

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
                param_id = i.get('parameterID', None)
                if param_id:
                    i = self.get_param_list(param_id)
                param_len = i['length']
                comment = i['comment']
                try:
                    value = req_param[comment]
                except KeyError:
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
                #                    if len(value) < 0xFF:
                #                         val_len = bytes.fromhex('{:02x}'.format(len(value)))
                #                    else:
                #                         val_len = bytes.fromhex('{:04x}'.format(len(value)))
                elif type(value) == bytes:
                    val = value
                else:
                    val = None
                if val:
                    data += val
        p = wp_parser.Parser()
        return p.generate_package(direction, cmd, data, ext_hdr, ext_len)

    def generate_get_response(self, raw_package: bytearray, variant: int = 0):
        c = self.get_element_by_cmd(raw_package['type'], raw_package['cmd'].hex().upper())
        if c is None:
            return None

        res = [(i, j, c[i][j]) for i in c for j in c[i]]
        category = res[0][0]
        sub = res[0][1]
        c = res[0][2]

        var = c['variations']
        cmd = c['command']

        raw = raw_package['data']
        pkg = list()
#        print(f'resp raw: {raw}')
        blk_len_check = None
        optional_param = None

        if len(var) <= variant:
            raise ValueError('variant out of range')

        req = var[variant]['reply']
        param = req['parameters']

        if len(param) != 0:
            start = 0
            end = 0

            rm_param = list()
            data_common = dict()
            if cmd == 'CBBA':  # Window 2 command
                f = ('Window reference width', 'Window reference height')
                rm_param = [i for i in param if i['comment'] in f]
#                print(raw[start:])
            elif cmd == 'CB90':  # Content Sources
                f = ('Number of sources')
                rm_param = [i for i in param if i['comment'] in f]
                blk_len_check = ('Source block length')
                optional_param = ('Type specific source block')
#                print(raw[start:].hex())

            for i in rm_param:
                param_len = i['length']
                comment = i['comment']
                if param_len:
                    end = start + param_len
                    data_common[comment] = int(raw[start:end].hex(), 16)
#                    print(f'{comment}: {data_common[comment]}')
                    prev_val = data_common[comment]
                    start = end

            if len(data_common):
                pkg.append(data_common)

            # I expect it is a repeating block when the raw package
            # size is not finish after first iteration over the parameters
            while end < len(raw):
#                print(f'end: {end}, rawlen: {len(raw)}')
                prev = None
                data = dict()
                blk_len = 0
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
                        i = self.get_param_list(param_id)
                    param_len = i['length']
                    comment = i['comment']
                    if param_len:
                        end = start + param_len
                        data[comment] = int(raw[start:end].hex(), 16)
                        prev_val = data[comment]
#                        print(f'1:{comment}: {prev_val} len: {param_len}')
                        if blk_len_check and comment in blk_len_check:
                            blk_len = 0
                    else:
                        # str_len + str
                        if prev and prev['comment'].find(comment) != -1:
                            # prev_val = string length
                            end = start + prev_val
#                            print(f'start: {start}, end: {end}')
                            data[comment] = raw[start:end]
#                            print(f'prev: {prev["comment"]}: {prev_val}')
#                            print(f'2:{comment}: {data[comment]} len: {param_len}')
                        else:
                            if optional_param and optional_param == comment:
                                end += (data[blk_len_check] - blk_len + 1)
                                data[comment] = raw[start:end]
#                                print(f' start {start} end: {end}')
                            else:
                                data[comment] = raw
#                                print(f'3:{comment}: {data[comment]} len: {param_len}')
                                end = len(raw)
                    prev = i
                    blk_len += end - start
                    start = end
#                    print(data)
                pkg.append(data)
        return category, sub, pkg

    def supported_device_idx_list(self, device_names: list):
        dev_list = list()
        if device_names is None:
            device_names = ['CB1']

        for dev in device_names:
            for sup_dev in self.supported_devices:
                if sup_dev['name'] == dev.upper():
                    dev_list.append(sup_dev['idx'])

        if len(dev_list) == 0:
            raise ValueError(f'device list is empty')
        return dev_list

    def add_template_parameter(self):
        if self.parameter is None:
            raise GeneratorExit('no template parameter generated')

        for param in self.param_list:
            if param['name'] == self.parameter['name']:
                raise IndexError(f'{self.parameter["name"]} already exists')

        self.param_list.append(self.parameter)
        self.parameter = None

    def add_value_to_template_parameter(self, comment: str, value: str, pub_comment: str = '', sup_dev=None):
        dev_list = self.supported_device_idx_list(sup_dev)

        value = dict(zip(['value', 'comment', 'publicComment', 'supportedDevices'],
                         [value, comment, pub_comment, dev_list]))
        self.parameter['values'].append(value)

    def generate_template_parameter(self, name: str, value: str, length: int, comment: str = '', pub_comment: str = ''):

        self.parameter = (dict(zip(['name', 'comment', 'publicComment', 'length', 'value', 'values'],
                                   [name, comment, pub_comment, length, value, list()])))

    def edit_userlevel_list(self, name: str, action: str, new_name: str = None):
        if action not in self.edit_actions:
            raise GeneratorExit(f'action {action} not in {self.edit_actions} list')

        if action == 'add':
            if name in self.userleves:
                raise ValueError('userlevel exists')
            self.userleves.append(name)
        elif action == 'rename':
            idx = self.userleves.index(name)
            self.userleves.insert(idx, new_name)
            self.userleves.remove(name)
        elif action == 'remove':
            self.userleves.remove(name)
        else:
            raise KeyError(f'action: {action} unknown - {self.edit_actions}')

    def edit_device_list(self, device_name: str, action: str, new_device_name: str = None):
        if action not in self.edit_actions:
            raise GeneratorExit(f'action {action} not in {self.edit_actions} list')

        if action == 'add':
            idx = 0
            for dev in self.supported_devices:
                if dev['name'] == device_name:
                    raise ValueError('device exists')
                if dev['idx'] >= idx:
                    idx = dev['idx'] + 1
            self.supported_devices.append({'name': device_name, 'idx': idx})
        elif action == 'edit':
            for dev in self.supported_devices:
                if dev['name'] == device_name:
                    dev['name'] = new_device_name
                    return
            raise ValueError('device not found')
        elif action == 'remove':
            for dev in self.supported_devices:
                if dev['name'] == device_name:
                    idx = self.supported_devices.index(dev)
                    self.supported_devices.pop(idx)
                    return
            raise ValueError('device not found')
        else:
            raise KeyError(f'action: {action} unknown - {self.edit_actions}')

    def edit_section(self, direction: str, section: str, action: str, new_section: str = None):

        if action not in self.edit_actions:
            raise GeneratorExit(f'action {action} not in {self.edit_actions} list')

        if direction not in self.direction_types:
            raise KeyError(f'{direction} - expect {self.direction_types}')

        if action == 'remove':
            self.root[direction]['categories'].pop(section)
        elif action == 'add':
            try:
                origin = self.root[direction]['categories'][section]
                if origin is not None:
                    raise GeneratorExit(section)
            except KeyError as err:
                if str(err).strip("'") != section:
                    raise

            self.root[direction]['categories'][section] = dict()
        elif action == 'rename':
            if new_section is None:
                raise KeyError('no new section name defined')
            self.root[direction]['categories'][new_section] = self.root[direction]['categories'].pop(section)
        else:
            raise KeyError(f'action: {action} unknown - {self.edit_actions}')

    def _section(self, direction: str, section: str):

        if direction not in self.direction_types:
            raise KeyError(f'{direction} - expect {self.direction_types}')

        try:
            origin = self.root[direction]['categories'][section]
            if origin is not None:
                raise GeneratorExit(section)
        except KeyError as err:
            if str(err).strip("'") != section:
                raise

        self.root[direction]['categories'][section] = dict()

    def generate_element(self, direction: str, cmd: str, section, name, public_name: str = '',
                         user_level: str = '0'):

        if direction not in self.direction_types:
            raise KeyError(f'{direction} - expect {self.direction_types}')

        _cmd = int(cmd.encode('utf-8'), 16)
        if _cmd > 255:
            _cmd = bytes.fromhex('{:04x}'.format(_cmd))
        else:
            _cmd = bytes.fromhex('{:02x}'.format(_cmd))
        _cmd = str(_cmd.hex()).upper()
        param = dict(zip(self.main_parameters,
                         [public_name, str(int(time.time() * 1000)), len(_cmd) // 2, _cmd, user_level, list()]))
        self.element = dict(
            zip(['direction', 'section', 'name', 'param'],
                ['GET' if direction == 'GET' else 'SET', section, name, param]))

    def add_variation(self, req_comment: str, req_pub_comment: str, reply_comment: str, reply_pub_comment: str,
                      req_ext_hdr: bool = False, req_ext_len: bool = False, reply_ext_hdr: bool = False,
                      reply_ext_len: bool = False, preliminary=False, secret=False, deprecated=False, tutorial=False):
        meta = dict(zip(['preliminary', 'secret', 'deprecated', 'tutorial'],
                        [preliminary, secret, deprecated, tutorial]))
        variations = self.element['param']['variations']
        idx = len(variations)
        variations.append(dict(zip(['meta', 'request', 'reply'],
                                   [meta, None, None])))

        wp = wp_parser.Parser()
        hdr = wp.generate_header_information(self.element['direction'], self.element['param']['command'], req_ext_hdr,
                                             req_ext_len)
        pkg = dict(zip(['headerLength', 'header', 'parameterLengthLength', 'comment', 'publicComment', 'parameters'],
                       [hdr[1], str(hdr[0]), hdr[2], req_comment, req_pub_comment, list()]))
        self.element['param']['variations'][idx]['request'] = pkg

        wp = wp_parser.Parser()
        hdr = wp.generate_header_information(self.element['direction'], self.element['param']['command'], reply_ext_hdr,
                                             reply_ext_len)
        pkg = dict(zip(['headerLength', 'header', 'parameterLengthLength', 'comment', 'publicComment', 'parameters'],
                       [hdr[1], str(hdr[0]), hdr[2], reply_comment, reply_pub_comment, list()]))
        self.element['param']['variations'][idx]['reply'] = pkg

        return idx

    def add_parameter_to_variant(self, variation_idx: int, pkg_type: str, value, length, comment, sup_dev: list = None,
                                 pub_comment: str = ''):
        if len(self.element['param']['variations']) < variation_idx:
            raise GeneratorExit('no variation found')

        if self.element['param']['variations'][variation_idx][pkg_type] is None:
            raise GeneratorExit('no package generated')

        dev_list = self.supported_device_idx_list(sup_dev)

        param = dict(zip(['value', 'length', 'comment', 'publicComment', 'supportedDevices', 'values'],
                         [value, length, comment, pub_comment, dev_list, list()]))
        parameters = self.element['param']['variations'][variation_idx][pkg_type]['parameters']
        idx = len(parameters)
        parameters.append(param)
        return idx

    def add_value_to_parameter(self, variation_idx: int, param_idx: int, pkg_type: str, comment: str, value: str = '',
                               sup_dev: list = None,
                               pub_comment: str = ''):
        if len(self.element['param']['variations']) < variation_idx:
            raise GeneratorExit('no variation found')

        if len(self.element['param']['variations'][variation_idx][pkg_type]['parameters']) < param_idx:
            raise GeneratorExit('no parameter foiund')

        dev_list = self.supported_device_idx_list(sup_dev)

        value = dict(zip(['value', 'comment', 'publicComment', 'supportedDevices'],
                         [value, comment, pub_comment, dev_list]))
        val_list = self.element['param']['variations'][variation_idx][pkg_type]['parameters'][param_idx]['values']
        idx = len(val_list)
        val_list.append(value)
        return idx

    def get_elements(self, direction, section=None, attr=None):

        if direction not in self.direction_types:
            raise KeyError(f'{direction} - expect {self.direction_types}')

        if section is None:
            sections = self.root[direction]['categories']
        else:
            sections = {section: ""}

        result = dict()
        for i in sections:
            elements = self.root[direction]['categories'][i]
            element = dict()
            for key in elements:
                values = [(j, elements[key][j]) for j in elements[key] if attr is None or j in attr]
                val = dict()
                for j in values:
                    val[j[0]] = j[1]
                element[key] = val
            result[i] = element

        return result

    def get_element_by_name(self, direction, section, name, attr=None):

        if direction not in self.direction_types:
            raise KeyError(f'{direction} - expect {self.direction_types}')

        elements = self.get_elements(direction, section, attr)
        if name is None:
            return elements

        result = dict()
        for i in elements:
            result[i] = dict()
            for j in elements[i]:
                if name == j:
                    result[i][j] = elements[i][j]
            if len(result[i]) == 0:
                result.pop(i)

        if len(result) == 0:
            return None
        else:
            return result

    def get_element_by_cmd(self, direction, cmd, attr=None) -> dict:
        if direction not in self.direction_types:
            raise KeyError(f'{direction} - expect {self.direction_types}')

        if attr:
            attr.append('command')
        elements = self.get_elements(direction, None, attr)
        res = [{i: {j: elements[i][j]}} for i in elements for j in elements[i]
               if elements[i][j]['command'] == cmd.upper()]
        if len(res) == 0:
            return None
        return res[0]

    def get_param_list(self, value=None):
        attr = 'idx' if type(value) is int else 'name'
        for i in self.param_list:
            if i[attr] == value:
                i['comment'] = i['name']
                return i
        return None

    def copy_element(self, direction, from_section, from_name, to_section, to_name, to_cmd, dump_file=False,
                     file_name=None):
        if direction not in self.direction_types:
            raise KeyError(f'{direction} - expect {self.direction_types}')

        original = self.root[direction]['categories'][from_section][from_name]
        if self.get_element_by_cmd(direction, to_cmd) is not None:
            raise IndexError('Command exists')
        else:
            new = original.copy()
            new['command'] = to_cmd
            self.root[direction]['categories'][to_section][to_name] = new
            if dump_file:
                self.dump_json(file_name)
        return new

    def add_element(self):
        try:
            if self.element is None:
                raise GeneratorExit('no element generated')

            original = self.root[self.element['direction']]['categories'][self.element['section']][self.element['name']]
            if original is not None:
                raise IndexError(f'{self.element["name"]} already exists')
        except KeyError as err:
            if str(err).strip("'") != self.element['name']:
                raise

        self.root[self.element['direction']]['categories'][self.element['section']][self.element['name']] = \
            self.element['param']
        self.element = None

    def remove_element(self, direction, section, name):
        self.root[direction]['categories'][section].pop(name)


if __name__ == '__main__':
    wd = Wolfdoc('wolfprot.json')
    sec = wd.get_elements('GET', 'Device', attr=[])  # , 'CB00', attr=['command', 'variations', 'userlevel'])
    #   print(sec)
    new = wd.copy_element('GET', 'Device', 'Model', 'Device', 'Model_New2', 'FFFF')

    wd.edit_device_list('CBC', 'remove')
    wd.edit_userlevel_list('Admin', 'rename', 'admin2')
    wd.generate_element('SET', 'CDCD', 'Device', 'Model2', '', '2')
    var_idx = wd.add_variation('req_comment', 'req_pub_comment', 'reply_comment', 'reply_pub_comment', True)
    param_idx = wd.add_parameter_to_variant(var_idx, 'request', 'n0..nn', 0, 'Name')
    wd.add_value_to_parameter(var_idx, param_idx, 'request', 'e.g. CB1', sup_dev=['CB1', 'CBC', 'CBP'])
    wd.add_value_to_parameter(var_idx, param_idx, 'request', 'e.g. CB2')

    param_idx = wd.add_parameter_to_variant(var_idx, 'request', 'a0', 0, 'Action')
    wd.add_value_to_parameter(var_idx, param_idx, 'request', 'Open File', '0x01')
    wd.add_value_to_parameter(var_idx, param_idx, 'request', 'Close File', '0x02')

    wd.add_element()
    wd.dump_json('wolfprot2.json')
    wd.remove_element('SET', 'Device', 'Model2')
    wd.edit_section('GET', 'Device2', 'add')
    wd.dump_json('wolfprot3.json')
    wd.generate_get_request('LAN Interface', 'LAN DHCP')
#   print(wdset.get_variation())
#   wdset.import_elem('GET', 'Device', 'Model', new)
#   wd.add_element('GET', 'Device', 'Model2', )
#   print(wdset.element)
