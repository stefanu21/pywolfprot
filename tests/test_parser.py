import json

from wolfprot import parser

TEST_DATA = 'tests/test_data.json'


def read_test_data(data=TEST_DATA):
    with open(data) as root:
        return json.load(root)


def read_test_result_header(test_json=None):
    json_obj = test_json['out']
    cmd_type = json_obj['cmd_type']
    return cmd_type.upper(), bytearray.fromhex(json_obj['cmd']), json_obj['data_start'], json_obj['data_end']


def read_test_result_data(test_json=None):
    json_obj = test_json['out']
    return json_obj['data']


def read_test_result_error(test_json=None):
    json_obj = test_json['out']
    return json_obj['error']


def read_test_input(test_json=None):
    return test_json['in']


def read_test_header_config(test_json=None):
    json_obj = test_json['out']
    return json_obj['ext_hdr'], json_obj['ext_len']


def test_A():
    t = read_test_data()
    for i in t:
        wv = parser.Parser()
        wv.append_buffer(read_test_input(t[i]))
        print(f'{i}')

        assert(wv.package_complete() is True)
        assert(wv.parse_header() == read_test_result_header(t[i]))
        assert(wv.get_data().hex() == read_test_result_data(t[i]))
        if read_test_result_error(t[i]) == 'None':
            err = None
        else:
            err = read_test_result_error(t[i])
        assert(wv.get_error() == err)


def test_B():
    t = read_test_data()
    for i in t:
        wv = parser.Parser()
        hdr = read_test_result_header(t[i])
        cfg = read_test_header_config(t[i])
        if read_test_result_error(t[i]) == 'None':
            err = None
        else:
            err = read_test_result_error(t[i])
        ret = wv.generate_package(hdr[0], hdr[1].hex(
        ), read_test_result_data(t[i]), cfg[0], cfg[1], err)
        result = bytes(ret.hex().encode('utf-8').upper()).decode('utf-8')

        assert(result == read_test_input(t[i]))


if __name__ == '__main__':
    test_A()
    test_B()
