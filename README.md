# PyWolfprot

It's a library to communicate with the WolfVision Cynap product family over socket or websocket

```Python

# examples
import wolfprot

#change box name
#wolfprot.json needed 
host = '192.168.100.45'
boxname = {'Name of box' : 'cynap-stefan'}
cb1 = wolfprot.cynap.Cynap(host, 1)
req = cb1.send_package('Device', 'Boxname', 0, boxname, 'GET', True)
print(req)

#firmware update

host = '192.168.100.45'
cb1 = wolfprot.cynap.Cynap(host, 1)
cb1.set_firmware_update('cb1.wgz')

```
