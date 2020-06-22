

class Parser:
    error_dict = {'01': 'Timeout',
                  '02': 'unknown command',
                  '03': 'unknown parameter',
                  '04': 'invalid length',
                  '05': 'fifo full',
                  '06': 'fw update',
                  '07': 'access denied',
                  '08': 'auth required',
                  '09': 'busy',
                  '0A': 'sip required',
                  '0B': 'power off',
                  }

    def __init__(self, byte_str=None):

        try:
            self.reset_buffers()
            if byte_str:
                self.append_buffer(self, byte_str)

        except ValueError as err:
            print("error: {0}".format(err))

    def reset_buffers(self):
        self.byte_str = ''
        self.cmd_type = None
        self.cmd = None
        self.data_start = None  # absolute
        self.data_end = None  # absolute
        self.error = None
        self.offset = 0

    def append_buffer(self, byte_str, offset=0):
        try:
            data_ = ''.join(
                ''.join(byte_str.casefold().split(sep='0x')).split())
        except ValueError as err:
            print("error: {0}".format(err))
            return -1

        self.byte_str += data_

        if self.cmd_type is None:
            self.cmd_type, self.cmd, self.data_start, self.data_end = self.parse_header(
                offset)
        return len(self.byte_str)*2

    def parse_header(self, offset=0):
        """

        """
        self.offset = offset
        self.cmd_type = None
        self.cmd = None
        self.data_start = None
        self.data_end = None
        self.error = None

        hdr_len = 3  # dir + cmd + len

        if offset > len(self.byte_str):
            raise ValueError('offset out of range')

        sub_byte_str = self.byte_str[offset:]

        if(len(sub_byte_str[0:]) < 2):
            return None, None, None, None

        byte_0 = int(sub_byte_str[0:2], 16)
        ext_hdr = None
        ext_len = None
        ext_cmd = None

        if byte_0 & 0x80:
            self.error = 1
        elif byte_0 & 0x02:  # dir + 0x01 + cmd + len
            ext_hdr = 1
            hdr_len += 1
        elif byte_0 & 0x04:
            ext_len = 1

        if byte_0 & 0x08:  # dir + cmd + cmd + len
            ext_cmd = 1
            hdr_len += 1

        if self.error is None:
            if len(sub_byte_str) < 4:
                return None, None, None, None
            byte_1 = int(sub_byte_str[2:4], 16)
            if ext_hdr and (byte_1 & 0x01):
                hdr_len += 3
            elif ext_len:
                hdr_len += 1

        if len(sub_byte_str) < hdr_len * 2:
            return None, None, None, None

        # aa cc ll dd
        cmd_start = 2
        len_start = 4
        data_start = 6
        cmd_type = None

        if ext_hdr:
            # aa 01 cc ll LL LL LL dd
            cmd_start += 2
            data_start += 8
            len_start += 2
        if ext_cmd:
            # aa cc CC ll dd
            len_start += 2
            data_start += 2
        if ext_len and ext_hdr is None:
            # aa cc ll LL dd
            data_start += 2

        if byte_0 & 0x01:
            cmd_type = 'SET'
        else:
            cmd_type = 'GET'

        cmd = sub_byte_str[cmd_start:len_start]

        if self.error:
            data_len = 1
            data_start = len_start
        else:
            data_len = int(sub_byte_str[len_start:data_start], 16)

        data_end = data_start + data_len * 2

        data_end += offset
        data_start += offset
        self.cmd_type = cmd_type
        self.cmd = cmd
        self.data_start = data_start
        self.data_end = data_end
        return cmd_type, cmd, data_start, data_end

    def package_complete(self):
        sub_byte_str = self.byte_str[self.offset:]
        if self.data_end is None or self.offset + len(sub_byte_str) < self.data_end:
            return False
        return True

    def header_complete(self):
        return self.cmd is not None

    def get_data(self):
        if not self.package_complete():
            return None
        return self.byte_str[self.data_start:self.data_end]

    def get_error(self):
        if self.package_complete() is False:
            return 'unknown'

        if self.error is None:
            return None
        return self.error_dict[self.get_data()]

    def generate_package(self, cmd_type, cmd, data, ext_hdr, ext_len):
        buf = ''
        byte_0 = 0

        if(len(data) % 2):
            raise ValueError('Odd-length string')

        if type(cmd) is str:
            cmd = ''.join(''.join(cmd.casefold().split(sep='0x')).split())
            cmd = int(cmd, 16)

        if cmd_type.casefold() == 'set':
            byte_0 = 0x01

        if(cmd > 0xFFFF):
            raise ValueError('command to long')
            return None
        elif(cmd > 0xFF):
            byte_0 += 0x08
            buf += '{:04x}'.format(cmd)
        else:
            buf += '{:02x}'.format(cmd)

        if ext_hdr:
            byte_0 += 0x02
            buf += '01'
            buf += '{:08x}'.format(len(data))
        elif ext_len:
            byte_0 += 0x04
            buf += '{:04x}'.format(len(data))
        else:
            if(len(data) > 0xFF):
                raise ValueError('data to long')
            buf += '{:02x}'.format(len(data) >> 1)

        buf = '{:02x}'.format(byte_0) + buf

        buf = buf + data

        self.append_buffer(buf)
        return buf
