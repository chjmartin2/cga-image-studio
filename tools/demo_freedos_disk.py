"""Repack the official FreeDOS 1.4 720K boot disk into a small demo disk.

Preserve its boot sector, KERNEL.SYS and FreeCOM bytes; omit installer/tools.
The distribution and corresponding sources/licenses are supplied alongside it.
"""
from pathlib import Path
from tools import make_marty_disk as fat
from tools.build_startlock import read_files


def read_tree(image):
    layout=fat.parse_layout(image)
    def chain(cluster):
        data=bytearray();seen=set()
        while 2 <= cluster < 0xff8:
            if cluster in seen or cluster > layout.data_cluster_count+1:
                raise ValueError('Invalid FAT chain')
            seen.add(cluster)
            pos=fat.cluster_offset(layout,cluster)
            data.extend(image[pos:pos+layout.cluster_size])
            cluster=fat.get_fat_entry(image,layout,cluster)
        return data
    found={}
    def directory(data,prefix=''):
        for offset in range(0,len(data),32):
            entry=data[offset:offset+32]
            if not entry or entry[0]==0:break
            if entry[0] in (0xe5,46) or entry[11]&8:continue
            raw=entry[:11].decode('ascii')
            name=raw[:8].rstrip()+('.'+raw[8:].rstrip() if raw[8:].strip() else '')
            payload=chain(int.from_bytes(entry[26:28],'little'))
            if entry[11]&16:directory(payload,prefix+name+'/')
            else:found[prefix+name]=bytes(payload[:int.from_bytes(entry[28:32],'little')])
    directory(image[layout.root_start:layout.data_start])
    return found


def build_disk(files, template):
    original=bytearray(Path(template).read_bytes())
    layout=fat.parse_layout(original)
    if len(original)!=720*1024 or original[3:11]!=b'FRDOS5.1' or original[510:512]!=b'\x55\xaa':
        raise ValueError('Expected official FreeDOS 1.4 720K boot image')
    source=read_tree(original)
    contents={'KERNEL.SYS':source['KERNEL.SYS'],
              'COMMAND.COM':source['FREEDOS/BIN/COMMAND.COM'],
              'FDCONFIG.SYS':b'BUFFERS=20\r\nFILES=30\r\nSHELL=\\COMMAND.COM /E:1024 /P=\\FDAUTO.BAT\r\n',
              'FDAUTO.BAT':b'@ECHO OFF\r\nSET COMSPEC=A:\\COMMAND.COM\r\nPROMPT $P$G\r\nMENU\r\n'}
    protected={'KERNEL.SYS','COMMAND.COM'}
    normalized={}
    for name,payload in files.items():
        fat.normalize_83(name)
        name=name.upper()
        if name in protected or name in normalized:raise ValueError('Duplicate/protected file: '+name)
        normalized[name]=payload
    contents.update(normalized)
    image=bytearray(len(original));image[:512]=original[:512]
    for index in range(layout.fat_count):
        at=layout.fat_start+index*layout.fat_size_bytes
        image[at:at+3]=bytes((layout.media_descriptor,255,255))
    for name,payload in contents.items():fat.inject_file(image,payload,name)
    if read_files(image)!=contents:raise ValueError('Disk read-back mismatch')
    return bytes(image)
