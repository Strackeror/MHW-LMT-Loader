import json
import struct
from . import Cstruct as CS
from io import BytesIO
from collections import OrderedDict

def readAt(data, offset, class_def):
    tell = data.tell()
    data.seek(offset)
    ret = class_def(data)
    data.seek(tell)
    return ret

def align(num, amount):
    return (num + (amount - 1)) & ~(amount - 1)

def pad(array, amount):
    padAmount = align(len(array), amount) - len(array)
    return array + b'\0' * padAmount

class LMT(CS.PyCStruct):
    fields = OrderedDict([
        ("magic", "byte[4]"),
        ("version", "short"),
        ("entry_count", "short"),
        ("unkn", "byte[8]"),
    ])

    def __init__(self, data, **kwargs):
        self.full_data = readAt(data, data.tell(), lambda d: d.read())
        super().__init__(data, **kwargs)
        self.animation_offsets = []
        for i in range(self.entry_count):
            self.animation_offsets += [struct.unpack('Q', data.read(8))[0]]
    
    def get_animation(self, id):
        if self.animation_offsets[id] == 0:
            return None
        return readAt(BytesIO(self.full_data), self.animation_offsets[id], AnimationBlock)
    
    def override_animation(self, id, animation):
        offset = len(self.full_data)
        offset = align(offset, 16)
        self.animation_offsets[id] = offset
        animation.update_offsets(offset)
        self.full_data = pad(self.full_data, 16) + animation.serialize()

    def serialize(self):
        ret = super().serialize()
        for offset in self.animation_offsets:
            ret += struct.pack('Q', offset)
        ret += self.full_data[len(ret):]
        return ret

class AnimationBlock(CS.PyCStruct):
    fields = OrderedDict([
        ("bone_paths_offset", "uint64"),
        ("bone_path_count", "int"),
        ("frame_count", "int"),
        ("loop_frame", "int"),
        ("unkn", "int[17]"),
        ("events_offset", "uint64")
    ])

    def __init__(self, data = None, **kw):
        super().__init__(data, **kw)
        if not data: return

        self.bone_paths = []
        for i in range(self.bone_path_count):
            self.bone_paths += [readAt(data, self.bone_paths_offset + len(BonePath()) * i, BonePath)]
        
        if self.events_offset:
            self.events = readAt(data, self.events_offset, Events)
            
    def update_offsets(self, offset):
        offset += len(self)
        offset = self.update_data_offsets(offset)
        return offset

    def update_data_offsets(self, offset):
        self.bone_paths_offset = offset
        self.bone_path_count = len(self.bone_paths)
        offset += self.bone_path_count * len(BonePath())
        for i, path in enumerate(self.bone_paths):
            path.buffer_size = len(path.buffer)
            if path.buffer_size:
                path.buffer_offset = offset 
            else:
                path.buffer_offset = 0
            offset = align(offset + path.buffer_size, 8)

        for path in self.bone_paths:
            if path.bounds:
                path.bounds_offset = offset
                offset += len(BonePath.Bounds())
            else:
                path.bounds_offset = 0

        self.events_offset = offset
        offset = self.events.update_offsets(offset)
        return offset
    
    def serialize(self, offset = None):
        if offset is not None:
            self.update_offsets(offset)
        ret = self.serialize_block()
        ret += self.serialize_data()
        return ret
    
    def serialize_block(self):
        return super().serialize()
    
    def serialize_data(self):
        ret = b''
        for path in self.bone_paths:
            ret += path.serialize()
        
        for path in self.bone_paths:
            ret += path.buffer
            ret = pad(ret, 8)

        for path in self.bone_paths:
            if path.bounds:
                ret += path.bounds.serialize()
        ret += self.events.serialize()
        return ret
        

class BonePath(CS.PyCStruct):
    class Bounds(CS.PyCStruct):
        fields = OrderedDict([
            ("mult", "float[4]"),
            ("add", "float[4]")
        ])

    fields = OrderedDict([
        ("buffer_type", "ubyte"),
        ("usage", "ubyte"),
        ("joint_type", "ubyte"),
        ("unkn", "ubyte"),
        ("bone_id", "int"),
        ("weight", "float"),
        ("buffer_size", "int"),
        ("buffer_offset", "int64"),
        ("reference_frame", "float[4]"),
        ("bounds_offset", "int64"),
    ])

    def __init__(self, data = None, **kw):
        super().__init__(data, **kw)
        if data:
            self.buffer = b''
            if self.buffer_size and self.buffer_offset:
                self.buffer = readAt(data, self.buffer_offset, lambda d: d.read(self.buffer_size))
            self.bounds = None
            if self.bounds_offset:
                self.bounds = readAt(data, self.bounds_offset, self.Bounds)
        


class Events(CS.PyCStruct):

    class Event(CS.PyCStruct):
        fields = OrderedDict([
            ("offset", "uint64"),
            ("count", "uint64"),
            ("type", "ubyte[8]")
        ])

    class Data(CS.PyCStruct):
        fields = OrderedDict([
            ('values', 'int[5]')
        ])

    fields = OrderedDict([
        ("categories_offset", "uint64"),
        ("category_count", "uint64"),
        ("unkn", "int[8]")
    ])


    def __init__(self, data = None, **kw):
        super().__init__(data, **kw)
        if not data:
            return
        
        self.categories = []
        for i in range(self.category_count):
            self.categories += [readAt(data, self.categories_offset + i * len(self.Event()), self.Event)]
        
        for category in self.categories:
            category.events = []
            for i in range(category.count):
                event = readAt(data, category.offset + i * len(self.Event()), self.Event)
                event.buffer = []
                for j in range(event.count):
                    event.buffer += [readAt(data, event.offset + j * len(self.Data()), self.Data)]
                category.events += [event]
    
    def update_offsets(self, offset):
        offset += len(self)
        self.categories_offset = offset
        self.category_count = len(self.categories)

        offset += len(self.Event()) * self.category_count
        offset = align(offset, 16)

        for category in self.categories:
            category.count = len(category.events)
            category.offset = offset
            offset += category.count * len(self.Event())
            offset = align(offset, 16)
        
        for category in self.categories:
            for event in category.events:
                event.count = len(event.buffer)
                event.offset = offset
                offset += event.count * len(self.Data())
                offset = align(offset, 16)

        return offset

    def serialize(self):
        ret = super().serialize()

        for category in self.categories:
            ret += category.serialize()
        ret = pad(ret, 16)


        for category in self.categories:
            for event in category.events:
                ret += event.serialize()
            ret = pad(ret, 16)
        
        for category in self.categories:
            for event in category.events:
                for data in event.buffer:
                    ret += data.serialize()
                ret = pad(ret, 16)

        return ret