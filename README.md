# PyWolfprot

It's a library to communicate with the WolfVision Cynap product family over socket or websocket

```Python
from wolfprot import connection
from wolfprot import wolfprot_get

#wp = connection.Socket('192.168.100.45', 1)
wp = connection.Websocket('wss://192.168.100.45/xxx', 'Password')
wp.login('Admin')
wolfprot_get.save_preview_pic(wp, '1280', '720', 'pic2.jpeg')
```