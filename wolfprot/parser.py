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
                self.append_buffer(byte_str)

        except ValueError as err:
            print("error: {0}".format(err))

    def reset_buffers(self):
        self.buffer = bytearray()
        self.cmd_type = None
        self.cmd = None
        self.data_start = None  # absolute
        self.data_end = None  # absolute
        self.error = None
        self.offset = 0

    def append_buffer(self, data, offset=0):
        try:
            if type(data) == str:
                data_ = bytes.fromhex(''.join(''.join(data.casefold().split(sep='0x')).split()))
                self.buffer.extend(data_)
            elif type(data) == bytes:
                self.buffer.extend(data)
        except ValueError as err:
            print("error: {0}".format(err))
            return -1

        if self.cmd_type is None:
            self.cmd_type, self.cmd, self.data_start, self.data_end = self.parse_header(
                offset)
        return len(self.buffer)

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

        if offset > len(self.buffer):
            raise ValueError('offset out of range')

        sub_buffer = self.buffer[offset:]

        if(len(sub_buffer) < 2):
            return None, None, None, None

        ext_hdr = None
        ext_len = None
        ext_cmd = None

        if self.buffer[0] & 0x80:
            self.error = 1
        elif self.buffer[0] & 0x02:  # dir + 0x01 + cmd + len
            ext_hdr = 1
            hdr_len += 1
        elif self.buffer[0] & 0x04:
            ext_len = 1

        if self.buffer[0] & 0x08:  # dir + cmd + cmd + len
            ext_cmd = 1
            hdr_len += 1

        if self.error is None:
            if len(sub_buffer) < 4:
                return None, None, None, None
            if ext_hdr and (self.buffer[1] & 0x01):
                hdr_len += 3
            elif ext_len:
                hdr_len += 1

        if len(sub_buffer) < hdr_len:
            return None, None, None, None

        if self.buffer[0] & 0x01:
            cmd_type = 'SET'
        else:
            cmd_type = 'GET'

        # aa cc ll dd
        cmd_start = 1
        len_start = 2
        data_start = 3

        if self.error:
            # aa cc DD
            data_start = 2
            if ext_cmd:
                # aa cc CC dd
                data_start += 1
            len_start = data_start
            data_end = data_start + 1
        else:
            if ext_hdr:
                # aa 01 cc ll LL LL LL dd
                cmd_start += 1
                data_start += 4
                len_start += 1
            if ext_cmd:
                # aa cc CC ll dd
                len_start += 1
                data_start += 1
            if ext_len and ext_hdr is None:
                # aa cc ll LL dd
                data_start += 1
            data_len = self.buffer[len_start:data_start]
            data_end = data_start + int(data_len.hex(), 16)

        cmd = self.buffer[cmd_start:len_start]

        data_end += offset
        data_start += offset
        self.cmd_type = cmd_type
        self.cmd = cmd
        self.data_start = data_start
        self.data_end = data_end
        return cmd_type, cmd, data_start, data_end

    def package_complete(self):
        sub_byte_str = self.buffer[self.offset:]
        if self.data_end is None or self.offset + len(sub_byte_str) < self.data_end:
            return False
        return True

    def header_complete(self):
        return self.cmd is not None

    def get_data(self):
        if not self.package_complete():
            return None
        return self.buffer[self.data_start:self.data_end]

    def get_header(self):
        if not self.package_complete():
            return None
        return self.buffer[:self.data_start]

    def get_error(self):
        if self.package_complete() is False:
            return 'unknown'

        if self.error is None:
            return None
        return self.error_dict[self.get_data().hex()]

    def generate_package(self, cmd_type, cmd, data, ext_hdr=None, ext_len=None, error=None):
        """
        return bytearray
        """
        buf = bytearray(1)

        if type(data) is bytes:
            data_ = bytearray(data)
        elif data is None:
            data_ = bytearray()
        elif type(data) is bytearray:
            data_ = data
        elif type(data) is str:
            if len(data) % 2:
                raise ValueError('Odd-length string')
            data_ = bytes.fromhex(''.join(''.join(data.casefold().split(sep='0x')).split()))
        else:
            raise ValueError('unknown type')

        if ((len(data_) > 0xFF) and ext_len is None) or (len(data_) > 0xFFFF and ext_hdr is None):
            raise ValueError('data to long')

        if type(cmd) is str:
            cmd = ''.join(''.join(cmd.casefold().split(sep='0x')).split())
            cmd = int(cmd, 16)
        elif type(cmd) is not int:
            raise ValueError('unexpected cmd type')

        if cmd_type.casefold() == 'set':
            buf[0] += 0x01

        if cmd > 0xFF:
            buf[0] += 0x08
            buf.extend(bytes.fromhex('{:04x}'.format(cmd)))
        else:
            buf.extend(bytes.fromhex('{:02x}'.format(cmd)))

        if error:
            buf[0] += 0x80
            err_nr = int(list(self.error_dict.keys())[list(self.error_dict.values()).index(error)], 16)
            data_ = bytes.fromhex('{:02x}'.format(err_nr))
        elif ext_hdr:

            buf[0] += 0x02
            buf.insert(1, 1)
            buf.extend(bytes.fromhex('{:08x}'.format(len(data_))))
        elif ext_len:
            buf[0] += 0x04
            buf.extend(bytes.fromhex('{:04x}'.format(len(data_))))
        else:
            buf.extend(bytes.fromhex('{:02x}'.format(len(data_))))

        buf.extend(data_)

        self.buffer.extend(buf)
        return buf
