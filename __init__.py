import bpy
import bpy_extras
import struct
from bpy.props import StringProperty, BoolProperty, EnumProperty
from mathutils import Vector, Quaternion, Matrix
from io import BytesIO
from .lmt.Lmt import LMT, AnimationBlock

bl_info = {"name": "LMT Importer", "category": "Animation"}

def lerp3(value, bounds):
    if (bounds is None):
        return value
    value = Vector(value[:])
    value = Vector(x * y for x, y in zip(value, bounds.mult[0:3]))
    return Vector(value + Vector(bounds.add[0:3]))

def lerpq(value, bounds):
    ret = Quaternion()
    mult = Vector(bounds.mult)
    add = Vector(bounds.add)
    ret.x = add.x + value.x * mult.x
    ret.y = add.y + value.y * mult.y
    ret.z = add.z + value.z * mult.z
    ret.w = add.w + value.w * mult.w
    return ret

def recompose(trs, rot, scl):
    return (
        Matrix.Translation(trs) * rot.to_matrix().to_4x4() 
        * Matrix.Scale(scl[0],4,(1, 0, 0)) 
        * Matrix.Scale(scl[1],4,(0, 1, 0)) 
        * Matrix.Scale(scl[2],4,(0, 0, 1))
    )

def structread(io, format):
    return list(struct.unpack(format, io.read(struct.calcsize(format))))

class QuantizedVals:
    def __init__(self, array, bit_per_elem = 8):
        self.array = [int(x) for x in array]
        self.bit_per_elem = bit_per_elem
        self.total_bits = len(array) * bit_per_elem
        self.elem_bits = bit_per_elem

    def skipbits(self, bitcount):
        while bitcount > 0:
            count = min(bitcount, self.elem_bits)
            self.elem_bits -= count
            bitcount -= count
            if self.elem_bits == 0:
                self.array = self.array[1:]
                self.elem_bits = self.bit_per_elem
            else:
                self.array[0] = self.array[0] >> count
        self.total_bits -= bitcount

    def loadbits(self, bitcount, scale = 0):
        val = 0
        bits_left = bitcount
        current_elem = 0
        current_bitcount = min(self.elem_bits, bits_left)
        while bits_left > 0:
            val = val << current_bitcount
            val = val | (self.array[current_elem] & ((1 << current_bitcount) - 1))
            bits_left -= current_bitcount
            current_elem += 1
            current_bitcount = min(self.bit_per_elem, bits_left)
            

        maxval = ((1 << bitcount) - 1)
        if scale == 1:
            val = val / maxval
        elif scale == -1:
            if val > (maxval >> 1):
                val -= maxval
            val = val / (maxval >> 1)
        return val

    def takebits(self, bitcount, scale = 0):
        ret = self.loadbits(bitcount, scale)
        self.skipbits(bitcount)
        return ret

class Key:
    #if type == 1:
    def baseFloatVectorKey(self, io, bounds):
        self.value = Vector(structread(io, "fff"))
        self.frame = 1
    #elif type == 2 or type == 3 or type == 9:
    def floatVectorKey(self, io, bounds):
        self.value = Vector(structread(io, "fff"))
        self.frame = structread(io, "I")[0]
    #elif type == 4:
    def shortVectorKey(self, io, bounds):
        self.value = Vector((x / 65535) for x in structread(io, "HHH"))
        self.frame = structread(io, "H")[0]
        self.value = lerp3(self.value, bounds)

    #elif type == 5:
    def byteVectorKey(self, io, bounds):
        self.value = Vector((x / 255) for x in structread(io, "BBB"))
        self.frame = structread(io, "B")[0]
        self.value = lerp3(self.value, bounds)

    #elif type == 6:
    def bits14QuaternionKey(self, io, bounds):
        values = QuantizedVals(structread(io, "Q"), 64)
        self.value = Quaternion((1, 0, 0, 0))
        self.value.w = values.takebits(14, -1) * 2
        self.value.z = values.takebits(14, -1) * 2
        self.value.y = values.takebits(14, -1) * 2
        self.value.x = values.takebits(14, -1) * 2
        self.frame = values.takebits(8)

    #elif type == 7:
    def bits7QuaternionKey(self, io, bounds):
        values = QuantizedVals(structread(io, "I"), 32)
        self.value = Quaternion((1, 0, 0, 0))
        self.value.w = values.takebits(7, 1)
        self.value.z = values.takebits(7, 1)
        self.value.y = values.takebits(7, 1)
        self.value.x = values.takebits(7, 1)
        self.frame = values.takebits(4)
        self.value = lerpq(self.value, bounds)

    #elif type == 11:
    def XWQuaternionKey(self, io, bounds):
        value = QuantizedVals(structread(io, "I"), 32)
        self.value = Quaternion((1, 0, 0, 0))
        if bounds is not None:
            self.value.x = value.takebits(14, 1)
            self.value.w = value.takebits(14, 1)
            self.value = lerpq(self.value, bounds)
        else:
            self.value.w = value.takebits(14) / 0xFFF
            self.value.x = value.takebits(14)
            if (self.value.x > 0x1fff != 0):
                self.value.x = -(0x1fff - self.value.x)
            self.value.x /= 0x8ff
        self.frame = value.takebits(4)
    #elif type == 12:
    def YWQuaternionKey(self, io, bounds):
        value = QuantizedVals(structread(io, "I"), 32)
        self.value = Quaternion((1, 0, 0, 0))
        if bounds is not None:
            self.value.y = value.takebits(14, 1)
            self.value.w = value.takebits(14, 1)
            self.value = lerpq(self.value, bounds)
        else:
            self.value.w = value.takebits(14) / 0xFFF
            self.value.y = value.takebits(14)
            if (self.value.y > 0x1fff != 0):
                self.value.y = -(0x1fff - self.value.y)
            self.value.y /= 0x8ff
        self.frame = value.takebits(4)
    #elif type == 13:
    def ZWQuaternionKey(self, io, bounds):
        value = QuantizedVals(structread(io, "I"), 32)
        self.value = Quaternion((1, 0, 0, 0))
        if bounds is not None:
            self.value.z = value.takebits(14, 1)
            self.value.w = value.takebits(14, 1)
            self.value = lerpq(self.value, bounds)
        else:
            self.value.w = value.takebits(14) / 0xFFF
            self.value.z = value.takebits(14)
            if (self.value.z > 0x1fff != 0):
                self.value.z = -(0x1fff - self.value.z)
            self.value.z /= 0x8ff
        self.frame = value.takebits(4)
    #elif type == 14:
    def bits11QuaternionKey(self, io, bounds):
        values = QuantizedVals(structread(io, "HHH"), 16)
        self.value = Quaternion((1, 0, 0, 0))
        self.value.x = values.takebits(11, 1)
        self.value.y = values.takebits(11, 1)
        self.value.z = values.takebits(11, 1)
        self.value.w = values.takebits(11, 1)
        self.frame = values.takebits(4)
        self.value = lerpq(self.value, bounds)
    #15
    def bits9QuaternionKey(self, io, bounds):
        values = QuantizedVals(io.read(5))
        self.value = Quaternion((1, 0, 0, 0))
        self.value.x = values.takebits(9, 1)
        self.value.y = values.takebits(9, 1)
        self.value.z = values.takebits(9, 1)
        self.value.w = values.takebits(9, 1)
        self.frame = values.takebits(4)
        self.value = lerpq(self.value, bounds)
    
    def __init__(self, io, type, bounds):
        [
            None,
            self.baseFloatVectorKey,
            self.floatVectorKey,
            self.floatVectorKey,
            self.shortVectorKey,
            self.byteVectorKey,
            self.bits14QuaternionKey,
            self.bits7QuaternionKey,
            None,
            self.floatVectorKey,
            None,
            self.XWQuaternionKey,
            self.YWQuaternionKey,
            self.ZWQuaternionKey,
            self.bits11QuaternionKey,
            self.bits9QuaternionKey
        ][type](io, bounds)


class BaseKey:
    def __init__(self, ref, usage):
        if usage == 0 or usage == 3: 
            self.value = Quaternion([ref[3]] + ref[0:3])
        else:
            self.value = Vector(ref[0:3])
        self.frame = 0

class KeyFrameList:
    def __init__(self, bone_path):
        key_frame_list = []
        io = BytesIO(bone_path.buffer)
        while io.tell() < len(bone_path.buffer):
            key_frame_list += [Key(io, bone_path.buffer_type, bone_path.bounds)]
        if not key_frame_list:
            key_frame_list += [BaseKey(bone_path.reference_frame, bone_path.usage)]
        self.bone_id = bone_path.bone_id
        self.usage = bone_path.usage
        self.keys = key_frame_list

        
class Animation:
    def __init__(self, animation_block : AnimationBlock, armature_obj):
        self.block = animation_block
        self.key_frames = [KeyFrameList(b) for b in animation_block.bone_paths]

        self.bone_map  = {-1: armature_obj.pose.bones[0]}
        for bone, edit_bone in zip(armature_obj.pose.bones, armature_obj.data.edit_bones):
            if "boneFunction" in edit_bone:
                bone["boneFunction"] = edit_bone["boneFunction"]
                self.bone_map[edit_bone["boneFunction"]] = bone
    
    def apply_animation(self, armature_obj):
        for key_frame_list in self.key_frames:
            if key_frame_list.bone_id not in self.bone_map:
                continue
            bone = self.bone_map[key_frame_list.bone_id]
            frameId = 0

            local_bone_matrix = bone.matrix
            if bone.parent:
                local_bone_matrix = armature_obj.convert_space(bone.parent, bone.matrix, 'POSE', 'LOCAL')
            
            if key_frame_list.usage == 0:
                for key in key_frame_list.keys:
                    trs, rot, scl = local_bone_matrix.decompose()
                    rot = key.value
                    nmatrix = recompose(trs, rot, scl)
                    bone.matrix = armature_obj.convert_space(bone.parent, nmatrix, 'LOCAL', 'POSE')
                    bone.keyframe_insert('rotation_quaternion', frame=frameId)
                    frameId += key.frame
            if key_frame_list.usage == 1:
                for key in key_frame_list.keys:
                    trs, rot, scl = local_bone_matrix.decompose()
                    trs = key.value
                    nmatrix = recompose(trs, rot, scl)
                    bone.matrix = armature_obj.convert_space(bone.parent, nmatrix, 'LOCAL', 'POSE')
                    bone.keyframe_insert('location', frame=frameId)
                    frameId += key.frame
            if key_frame_list.usage == 3:
                for key in key_frame_list.keys:
                    trs, rot, scl = bone.matrix.decompose()
                    rot = key.value
                    bone.matrix = recompose(trs, rot, scl)
                    bone.keyframe_insert('rotation_quaternion', frame=frameId)
                    frameId += key.frame
            if key_frame_list.usage == 4:
                for key in key_frame_list.keys:
                    trs, rot, scl = bone.matrix.decompose()
                    trs = key.value
                    bone.matrix = recompose(trs, rot, scl)
                    bone.keyframe_insert('location', frame=frameId)
                    frameId += key.frame
        
class LmtImportOperator(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "custom_import.import_lmt"
    bl_label = "Import LMT Animation"
    bl_options = {'REGISTER', 'PRESET', 'UNDO'}

    filename_ext = ".lmt"
    filter_glob = StringProperty(default="*.lmt", options={'HIDDEN'}, maxlen=255)
    animation_id = StringProperty(default="*", maxlen=20, name="Animation ID", description="'*' to load all animations, otherwise one number")

    def execute(self, context):
        lmt = LMT(open(self.properties.filepath, 'rb'))
        for obj in context.scene.objects:
            if (obj.type == 'ARMATURE'):
                armature_obj = obj
                break
        if not armature_obj:
            return
        context.scene.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')


        armature_obj.animation_data_create()
        ids_to_extract = range(lmt.entry_count)
        if self.animation_id != "*":
            ids_to_extract = [int(self.animation_id)]
        for id in ids_to_extract:
            animation = lmt.get_animation(id)
            if animation:
                print('\rLoading animation %03d / %03d' % (id, lmt.entry_count), end='')
                animation = Animation(animation, armature_obj)
                for bone in armature_obj.pose.bones:
                    bone.matrix_basis = Matrix()
                armature_obj.animation_data.action = bpy.data.actions.new("Animation %03d" % id)
                animation.apply_animation(armature_obj)

        bpy.ops.object.mode_set(mode='POSE')
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(LmtImportOperator.bl_idname, text="MHW LMT (.lmt)")

def register():
    bpy.utils.register_class(LmtImportOperator)
    bpy.types.INFO_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(LmtImportOperator)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
