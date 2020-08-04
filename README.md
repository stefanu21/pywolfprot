# PyWolfprot

It's a library to communicate with the WolfVision Cynap product family over socket or websocket

## Examples
```python
import wolfprot

#change box name
#wolfprot.json needed 
host = '192.168.100.45'
doc_file = wolfprot.cynap.doc_parser()
boxname = {'Name of box' : 'cynap-stefan'}
req = doc_file.get_request('Device', 'Boxname', 0, boxname, False)
cb1 = wolfprot.cynap.Cynap(host, 1)
print(doc_file.get_response(cb1.raw_package(req.pop())))

#firmware update

host = '192.168.100.45'
cb1 = wolfprot.cynap.Cynap(host, 1)
cb1.set_firmware_update('cb1.wgz')

```
