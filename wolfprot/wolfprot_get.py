
def preview_pic(wp, width, height):
    data = wp.send_package('get', 0xcb02, '{:04x}'.format(
        int(width)) + '{:04x}'.format(int(height)) + '0000')
    print(f'error: {wp.get_error()}')
    return bytes.fromhex(data[16:])


def save_preview_pic(wp, width, height, file):
    with open(file, 'wb') as f:
        p = preview_pic(wp, width, height)
        f.write(p)
