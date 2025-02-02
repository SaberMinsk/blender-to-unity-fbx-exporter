bl_info = {
	"name": "Unity FBX format",
	"author": "Angel 'Edy' Garcia (@VehiclePhysics)",
	"version": (1, 3, 1),
	"blender": (2, 80, 0),
	"location": "File > Export > Unity FBX",
	"description": "FBX exporter compatible with Unity's coordinate and scaling system.",
	"warning": "",
	"wiki_url": "",
	"category": "Import-Export",
}


import bpy
import mathutils
import math


# Multi-user datablocks are preserved here. Unique copies are made for applying the rotation.
# Eventually multi-user datablocks become single-user and gets processed.
# Therefore restoring the multi-user data assigns a shared but already processed datablock.
shared_data = dict()

# All objects and collections in this view layer must be visible while being processed.
# apply_rotation and matrix changes don't have effect otherwise.
# Visibility will be restored right before saving the FBX.
hidden_collections = []
hidden_objects = []
disabled_collections = []
disabled_objects = []


def unhide_collections(col):
	global hidden_collections
	global disabled_collections

	# No need to unhide excluded collections. Their objects aren't included in current view layer.
	if col.exclude:
		return

	# Find hidden child collections and unhide them
	hidden = [item for item in col.children if not item.exclude and item.hide_viewport]
	for item in hidden:
		item.hide_viewport = False

	# Add them to the list so they could be restored later
	hidden_collections.extend(hidden)

	# Same with the disabled collections
	disabled = [item for item in col.children if not item.exclude and item.collection.hide_viewport]
	for item in disabled:
		item.collection.hide_viewport = False

	disabled_collections.extend(disabled)

	# Recursively unhide child collections
	for item in col.children:
		unhide_collections(item)


def unhide_objects():
	global hidden_objects
	global disabled_objects

	view_layer_objects = [ob for ob in bpy.data.objects if ob.name in bpy.context.view_layer.objects]

	for ob in view_layer_objects:
		if ob.hide_get():
			hidden_objects.append(ob)
			ob.hide_set(False)
		if ob.hide_viewport:
			disabled_objects.append(ob)
			ob.hide_viewport = False


def make_single_user_data():
	global shared_data

	for ob in bpy.data.objects:
		if ob.data and ob.data.users > 1:
			if ob.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}:
				# Figure out the objects that use this datablock
				users = [user for user in bpy.data.objects if user.data == ob.data]

				# Shared data will be restored if users have no active modifiers
				modifiers = 0
				for user in users:
					modifiers += len([mod for mod in user.modifiers if mod.show_viewport])
				if modifiers == 0:
					shared_data[ob.name] = ob.data

			# Make single-user copy
			ob.data = ob.data.copy()


def apply_object_modifiers():
	# Select objects in current view layer not using an armature modifier
	bpy.ops.object.select_all(action='DESELECT')
	for ob in bpy.data.objects:
		if ob.name in bpy.context.view_layer.objects:
			bypass_modifiers = False
			for mod in ob.modifiers:
				if mod.type == 'ARMATURE':
					bypass_modifiers = True
			if not bypass_modifiers:
				ob.select_set(True)

	# Conversion to mesh may not be available depending on the remaining objects
	if bpy.ops.object.convert.poll():
		bpy.ops.object.convert(target='MESH')


def reset_parent_inverse(ob):
	if (ob.parent):
		mat_world = ob.matrix_world.copy()
		ob.matrix_parent_inverse.identity()
		ob.matrix_basis = ob.parent.matrix_world.inverted() @ mat_world


def apply_rotation(ob):
	bpy.ops.object.select_all(action='DESELECT')
	ob.select_set(True)
	bpy.ops.object.transform_apply(location = False, rotation = True, scale = False)


def fix_object(ob):
	# Only fix objects in current view layer
	if ob.name in bpy.context.view_layer.objects:

		# Reset parent's inverse so we can work with local transform directly
		reset_parent_inverse(ob)

		# Create a copy of the local matrix and set a pure X-90 matrix
		mat_original = ob.matrix_local.copy()
		ob.matrix_local = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X')

		# Apply the rotation to the object
		apply_rotation(ob)

		# Reapply the previous local transform with an X+90 rotation
		ob.matrix_local = mat_original @ mathutils.Matrix.Rotation(math.radians(90.0), 4, 'X')
		#ob.matrix_local = mathutils.Matrix.Rotation(math.radians(90.0), 4, 'X')
		
		if ob.type == 'EMPTY':
			if ob.animation_data != None:
				if ob.animation_data.action != None:
					fix_animation(ob)
	
	# Recursively fix child objects in current view layer.
	# Children may be in the current view layer even if their parent isn't.
	for child in ob.children:
		fix_object(child)


def fix_animation_euler(ob):
    print('...E...')
    tmp_data_frams_x = []
    tmp_data_value_x = []
    tmp_data_frams_y = []
    tmp_data_value_y = []
    tmp_data_frams_z = []
    tmp_data_value_z = []
        
    #xyz collect
    for point in ob.animation_data.action.fcurves[0].keyframe_points:
        tmp_data_frams_x.append(point.co.x)
        tmp_data_value_x.append(point.co.y)
    for point in ob.animation_data.action.fcurves[1].keyframe_points:
        tmp_data_frams_y.append(point.co.x)
        tmp_data_value_y.append(point.co.y)
    for point in ob.animation_data.action.fcurves[2].keyframe_points:
        tmp_data_frams_z.append(point.co.x)
        tmp_data_value_z.append(point.co.y)
        
    #create new action
    new_name = ob.animation_data.action.name + '_tmp'
    bpy.data.actions.new(new_name)
    ob.animation_data.action = bpy.data.actions.get(new_name)
    ob.keyframe_insert(data_path="rotation_euler", frame=-1)

    #insert conwert action
    for i in range(len(tmp_data_frams_x)):
        bpy.data.actions[new_name].fcurves[0].keyframe_points.insert(tmp_data_frams_x[i],tmp_data_value_x[i])
    for i in range(len(tmp_data_frams_y)):
        bpy.data.actions[new_name].fcurves[2].keyframe_points.insert(tmp_data_frams_y[i],tmp_data_value_y[i] * -1)
    for i in range(len(tmp_data_frams_z)):
        bpy.data.actions[new_name].fcurves[1].keyframe_points.insert(tmp_data_frams_z[i],tmp_data_value_z[i])


def fix_animation_quaternion(ob):
    print('...Q...')
    tmp_data_frams_w = []
    tmp_data_value_w = []
    tmp_data_frams_x = []
    tmp_data_value_x = []
    tmp_data_frams_y = []
    tmp_data_value_y = []
    tmp_data_frams_z = []
    tmp_data_value_z = []
        
    #xyz collect
    for point in ob.animation_data.action.fcurves[0].keyframe_points:
        tmp_data_frams_w.append(point.co.x)
        tmp_data_value_w.append(point.co.y)
    for point in ob.animation_data.action.fcurves[1].keyframe_points:
        tmp_data_frams_x.append(point.co.x)
        tmp_data_value_x.append(point.co.y)
    for point in ob.animation_data.action.fcurves[2].keyframe_points:
        tmp_data_frams_y.append(point.co.x)
        tmp_data_value_y.append(point.co.y)
    for point in ob.animation_data.action.fcurves[3].keyframe_points:
        tmp_data_frams_z.append(point.co.x)
        tmp_data_value_z.append(point.co.y)
    
        
    #create new action
    new_name = ob.animation_data.action.name + '_tmp'
    bpy.data.actions.new(new_name)
    ob.animation_data.action = bpy.data.actions.get(new_name)
    ob.keyframe_insert(data_path="rotation_quaternion", frame=-1)

    #insert conwert action
    for i in range(len(tmp_data_frams_x)):
        bpy.data.actions[new_name].fcurves[0].keyframe_points.insert(tmp_data_frams_w[i],tmp_data_value_w[i])
    for i in range(len(tmp_data_frams_y)):
        bpy.data.actions[new_name].fcurves[3].keyframe_points.insert(tmp_data_frams_y[i],tmp_data_value_y[i] * -1)
    for i in range(len(tmp_data_frams_z)):
        bpy.data.actions[new_name].fcurves[2].keyframe_points.insert(tmp_data_frams_z[i],tmp_data_value_z[i])
    for i in range(len(tmp_data_frams_x)):
        bpy.data.actions[new_name].fcurves[1].keyframe_points.insert(tmp_data_frams_x[i],tmp_data_value_x[i])

def fix_animation(ob):
    if ob.animation_data.action.fcurves[0].data_path == 'rotation_euler':
        fix_animation_euler(ob)
    else:
        fix_animation_quaternion(ob)

def export_unity_fbx(context, filepath, active_collection, selected_objects, bake_action):
	global shared_data
	global hidden_collections
	global hidden_objects
	global disabled_collections
	global disabled_objects

	print("Preparing 3D model for Unity...")

	# Root objects: Empty, Mesh or Armature without parent
	root_objects = [item for item in bpy.data.objects if (item.type == "EMPTY" or item.type == "MESH" or item.type == "ARMATURE") and not item.parent]

	# Preserve current scene
	# undo_push examples, including exporters' execute:
	# https://programtalk.com/python-examples/bpy.ops.ed.undo_push  (Examples 4, 5 and 6)
	# https://sourcecodequery.com/example-method/bpy.ops.ed.undo  (Examples 1 and 2)

	bpy.ops.ed.undo_push(message="Prepare Unity FBX")

	shared_data = dict()
	hidden_collections = []
	hidden_objects = []
	disabled_collections = []
	disabled_objects = []

	selection = bpy.context.selected_objects

	# Object mode
	bpy.ops.object.mode_set(mode="OBJECT")

	# Ensure all the collections and objects in this view layer are visible
	unhide_collections(bpy.context.view_layer.layer_collection)
	unhide_objects()

	# Create a single copy in multi-user datablocks. Will be restored after fixing rotations.
	make_single_user_data()

	# Apply modifiers to objects (except those affected by an armature)
	apply_object_modifiers()

	try:
		# Fix rotations
		for ob in root_objects:
			print(ob.name)
			fix_object(ob)

		# Restore multi-user meshes
		for item in shared_data:
			bpy.data.objects[item].data = shared_data[item]

		# Recompute the transforms out of the changed matrices
		bpy.context.view_layer.update()

		# Restore hidden and disabled objects
		for ob in hidden_objects:
			ob.hide_set(True)
		for ob in disabled_objects:
			ob.hide_viewport = True

		# Restore hidden and disabled collections
		for col in hidden_collections:
			col.hide_viewport = True
		for col in disabled_collections:
			col.collection.hide_viewport = True

		# Restore selection
		bpy.ops.object.select_all(action='DESELECT')
		for ob in selection:
			ob.select_set(True)

		# Export FBX file

		params = dict(filepath=filepath,
                      apply_scale_options='FBX_SCALE_UNITS',
                      object_types={'EMPTY', 'MESH', 'ARMATURE'},
                      use_active_collection=active_collection,
                      use_selection=selected_objects,
                      use_armature_deform_only=True,
                      add_leaf_bones=False,
                      bake_anim=bake_action,
                      bake_anim_use_all_bones=False,
                      bake_anim_use_nla_strips=False,
                      bake_anim_use_all_actions=False,
                      bake_anim_force_startend_keying=False,
                      bake_anim_step=1.0,
                      bake_anim_simplify_factor=0.0
                      )

		print("Invoking default FBX Exporter:", params)
		bpy.ops.export_scene.fbx(**params)

	except Exception as e:
		bpy.ops.ed.undo_push(message="")
		bpy.ops.ed.undo()
		bpy.ops.ed.undo_push(message="Export Unity FBX")
		print(e)
		print("File not saved.")
		# Always finish with 'FINISHED' so Undo is handled properly
		return {'FINISHED'}

	# Restore scene and finish

	bpy.ops.ed.undo_push(message="")
	bpy.ops.ed.undo()
	bpy.ops.ed.undo_push(message="Export Unity FBX")
	print("FBX file for Unity saved.")
	return {'FINISHED'}


#---------------------------------------------------------------------------------------------------
# Exporter stuff (from the Operator File Export template)

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator


class ExportUnityFbx(Operator, ExportHelper):
	"""FBX exporter compatible with Unity's coordinate and scaling system"""
	bl_idname = "export_scene.unity_fbx"
	bl_label = "Export Unity FBX"
	bl_options = {'UNDO_GROUPED'}

	# ExportHelper mixin class uses this
	filename_ext = ".fbx"

	filter_glob: StringProperty(
		default="*.fbx",
		options={'HIDDEN'},
		maxlen=255,  # Max internal buffer length, longer would be clamped.
	)

	# List of operator properties, the attributes will be assigned
	# to the class instance from the operator settings before calling.

	active_collection: BoolProperty(
		name="Active Collection Only",
		description="Export objects in the active collection only (and its children). May be combined with Selected Objects Only.",
		default=False,
	)

	selected_objects: BoolProperty(
		name="Selected Objects Only",
		description="Export selected objects only. May be combined with Active Collection Only.",
		default=False,
	)
	
	bake_action: BoolProperty(
		name="Bake Active Action",
		description="Export active action only.",
		default=False,
	)

	# Custom draw method
	# https://blender.stackexchange.com/questions/55437/add-gui-elements-to-exporter-window
	# https://docs.blender.org/api/current/bpy.types.UILayout.html

	def draw(self, context):
		layout = self.layout
		row = layout.row()
		row.label(text = "Selection")
		row = layout.row()
		row.prop(self, "active_collection")
		row = layout.row()
		row.prop(self, "selected_objects")
		row = layout.row()
		row.prop(self, "bake_action")


	def execute(self, context):
		return export_unity_fbx(context, self.filepath, self.active_collection, self.selected_objects, self.bake_action)


# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
	self.layout.operator(ExportUnityFbx.bl_idname, text="Unity FBX (.fbx)")


def register():
	bpy.utils.register_class(ExportUnityFbx)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
	bpy.utils.unregister_class(ExportUnityFbx)
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
	register()

	# test call
	bpy.ops.export_scene.unity_fbx('INVOKE_DEFAULT')
