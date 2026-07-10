import os
import re

import bpy
from bpy.types import PropertyGroup, UIList, Panel, Operator, Object, Action
from bpy.props import (
    StringProperty,
    BoolProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
)

from .builder import PsaBuilder, PsaBuilderOptions
from .exporter import PsaExporter


def _poll_armature(self, obj):
    return obj.type == 'ARMATURE'


def _poll_action_for_entry(self, action):
    """Restrict the action dropdown to actions that actually target the
    entry's chosen armature (mirrors PsaExportOperator.is_action_for_armature).
    If no armature has been chosen yet, don't filter anything out."""
    if self.armature is None or self.armature.type != 'ARMATURE':
        return True
    if len(action.fcurves) == 0:
        return False
    bone_names = {b.name for b in self.armature.data.bones}
    for fcurve in action.fcurves:
        match = re.match(r'pose\.bones\["(.+)"\]\.\w+', fcurve.data_path)
        if match and match.group(1) in bone_names:
            return True
    return False


class PsaActionLinkEntry(PropertyGroup):
    """One (armature, action) pair belonging to a link."""
    armature: PointerProperty(
        type=Object,
        name='Armature',
        description='Armature that owns the action below',
        poll=_poll_armature,
    )
    action: PointerProperty(
        type=Action,
        name='Action',
        description='Action to export for this armature',
        poll=_poll_action_for_entry,
    )
    invert_root_rotation: BoolProperty(
        name='Invert Root',
        description='Rotate this action\'s root bone 180 degrees on export. '
                    'Use this if this particular rig/action was authored '
                    'facing the opposite way from the rest',
        default=False,
    )


class PsaActionLink(PropertyGroup):
    """A named group of actions, from possibly different armatures, that
    should always be exported together (e.g. a character reload animation
    and the matching weapon reload animation)."""
    name: StringProperty(name='Name', default='Link')
    is_selected: BoolProperty(name='Export', default=True)
    entries: CollectionProperty(type=PsaActionLinkEntry)
    entries_index: IntProperty(default=0)


class PSA_UL_ActionLinkList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, 'is_selected', text='')
        row.prop(item, 'name', text='', emboss=False)
        row.label(text=f'{len(item.entries)} action(s)')


class PSA_UL_ActionLinkEntryList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, 'armature', text='')
        row.prop(item, 'action', text='')
        row.prop(item, 'invert_root_rotation', text='', icon='MOD_MIRROR', toggle=True)


class PSA_OT_action_link_add(Operator):
    bl_idname = 'psa.action_link_add'
    bl_label = 'Add Link'
    bl_description = 'Create a new action link group'

    def execute(self, context):
        link = context.scene.psa_action_links.add()
        link.name = f'Link {len(context.scene.psa_action_links)}'
        context.scene.psa_action_links_index = len(context.scene.psa_action_links) - 1
        return {'FINISHED'}


class PSA_OT_action_link_remove(Operator):
    bl_idname = 'psa.action_link_remove'
    bl_label = 'Remove Link'
    bl_description = 'Remove the selected action link group'

    @classmethod
    def poll(cls, context):
        return len(context.scene.psa_action_links) > 0

    def execute(self, context):
        index = context.scene.psa_action_links_index
        context.scene.psa_action_links.remove(index)
        context.scene.psa_action_links_index = max(0, index - 1)
        return {'FINISHED'}


class PSA_OT_action_link_duplicate(Operator):
    bl_idname = 'psa.action_link_duplicate'
    bl_label = 'Duplicate Link'
    bl_description = 'Duplicate the selected link, including all of its entries'

    @classmethod
    def poll(cls, context):
        return len(context.scene.psa_action_links) > 0

    def execute(self, context):
        links = context.scene.psa_action_links
        index = context.scene.psa_action_links_index
        source = links[index]

        new_link = links.add()
        new_link.name = f'{source.name} Copy'
        new_link.is_selected = source.is_selected

        # Copy over each entry's armature/action assignment as-is; the idea
        # is you only need to swap out the actions afterwards.
        for entry in source.entries:
            new_entry = new_link.entries.add()
            new_entry.armature = entry.armature
            new_entry.action = entry.action
            new_entry.invert_root_rotation = entry.invert_root_rotation

        # The new link lands at the end of the collection by default; move it
        # to sit right after the link it was copied from, and select it.
        new_index = len(links) - 1
        links.move(new_index, index + 1)
        context.scene.psa_action_links_index = index + 1

        return {'FINISHED'}


class PSA_OT_action_link_apply(Operator):
    bl_idname = 'psa.action_link_apply'
    bl_label = 'Apply Link'
    bl_description = (
        'Assign each entry\'s action to its armature as the active action, '
        'and match the scene frame range to it, so you can preview them '
        'together right away'
    )

    @classmethod
    def poll(cls, context):
        if len(context.scene.psa_action_links) == 0:
            return False
        link = context.scene.psa_action_links[context.scene.psa_action_links_index]
        return len(link.entries) > 0

    def execute(self, context):
        link = context.scene.psa_action_links[context.scene.psa_action_links_index]

        applied = 0
        frame_range = None

        for entry in link.entries:
            if entry.armature is None or entry.action is None:
                continue

            armature = entry.armature
            if armature.animation_data is None:
                armature.animation_data_create()
            armature.animation_data.action = entry.action
            applied += 1

            if frame_range is None:
                frame_range = entry.action.frame_range

        if applied == 0:
            self.report({'WARNING'}, f'Link "{link.name}" has no complete entries to apply.')
            return {'CANCELLED'}

        if frame_range is not None:
            context.scene.frame_start = int(frame_range[0])
            context.scene.frame_end = int(frame_range[1])
            context.scene.frame_set(int(frame_range[0]))

        self.report({'INFO'}, f'Applied {applied} action(s) from "{link.name}"')
        return {'FINISHED'}


class PSA_OT_action_link_entry_add(Operator):
    bl_idname = 'psa.action_link_entry_add'
    bl_label = 'Add Entry'
    bl_description = 'Add an armature/action pair to the selected link'

    @classmethod
    def poll(cls, context):
        return len(context.scene.psa_action_links) > 0

    def execute(self, context):
        link = context.scene.psa_action_links[context.scene.psa_action_links_index]
        entry = link.entries.add()
        # Convenience default: use the currently active armature, if any.
        active = context.view_layer.objects.active
        if active is not None and active.type == 'ARMATURE':
            entry.armature = active
        link.entries_index = len(link.entries) - 1
        return {'FINISHED'}


class PSA_OT_action_link_entry_remove(Operator):
    bl_idname = 'psa.action_link_entry_remove'
    bl_label = 'Remove Entry'
    bl_description = 'Remove the selected entry from the selected link'

    @classmethod
    def poll(cls, context):
        if len(context.scene.psa_action_links) == 0:
            return False
        link = context.scene.psa_action_links[context.scene.psa_action_links_index]
        return len(link.entries) > 0

    def execute(self, context):
        link = context.scene.psa_action_links[context.scene.psa_action_links_index]
        link.entries.remove(link.entries_index)
        link.entries_index = max(0, link.entries_index - 1)
        return {'FINISHED'}


class PSA_PT_action_linker(Panel):
    bl_idname = 'PSA_PT_action_linker'
    bl_label = 'PSA Action Linker'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PSA'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row()
        row.template_list(
            'PSA_UL_ActionLinkList', '',
            scene, 'psa_action_links',
            scene, 'psa_action_links_index',
            rows=4,
        )
        col = row.column(align=True)
        col.operator('psa.action_link_add', icon='ADD', text='')
        col.operator('psa.action_link_remove', icon='REMOVE', text='')
        col.separator()
        col.operator('psa.action_link_duplicate', icon='DUPLICATE', text='')

        if len(scene.psa_action_links) == 0:
            layout.label(text='Create a link to pair up actions across armatures.')
            return

        link = scene.psa_action_links[scene.psa_action_links_index]

        box = layout.box()
        header_row = box.row()
        header_row.label(text=f'Entries for "{link.name}"', icon='ACTION')
        header_row.operator('psa.action_link_apply', icon='CHECKMARK', text='Apply')
        row = box.row()
        row.template_list(
            'PSA_UL_ActionLinkEntryList', '',
            link, 'entries',
            link, 'entries_index',
            rows=4,
        )
        col = row.column(align=True)
        col.operator('psa.action_link_entry_add', icon='ADD', text='')
        col.operator('psa.action_link_entry_remove', icon='REMOVE', text='')

        # Sanity check: warn if actions in this link don't share a frame range,
        # which usually means they've drifted out of sync with each other.
        frame_ranges = set()
        for entry in link.entries:
            if entry.action is not None:
                frame_ranges.add(tuple(entry.action.frame_range))
        if len(frame_ranges) > 1:
            warning_row = box.row()
            warning_row.alert = True
            warning_row.label(text='Frame ranges differ within this link!', icon='ERROR')

        layout.separator()
        layout.operator('psa.export_linked', icon='EXPORT', text='Export Linked Actions')


def _merge_psa(base_psa, addition_psa):
    """Merge addition_psa's sequences and keys into base_psa, offsetting
    frame_start_index so the appended sequences point at the right place
    in the combined keys array. Bones are left as base_psa's, since the
    bind pose is identical for a given armature regardless of the invert
    flag (that flag only affects animation keys, not the rest pose)."""
    if base_psa is None:
        return addition_psa
    if addition_psa is None or len(addition_psa.sequences) == 0:
        return base_psa

    keys_per_frame = addition_psa.sequences[0].bone_count
    frame_offset = 0
    if keys_per_frame > 0 and len(base_psa.keys) > 0:
        frame_offset = len(base_psa.keys) // keys_per_frame

    for sequence in addition_psa.sequences:
        sequence.frame_start_index += frame_offset

    base_psa.sequences.extend(addition_psa.sequences)
    base_psa.keys.extend(addition_psa.keys)
    return base_psa


class PSA_OT_export_linked(Operator):
    bl_idname = 'psa.export_linked'
    bl_label = 'Export Linked Actions'
    bl_description = (
        'Export one .psa file per armature referenced by the selected links, '
        'each file containing all of the actions linked to that armature. '
        'Each exported sequence is named after its link, so a character '
        'action and its matching weapon action end up with the same '
        'in-game animation name even though the Blender action names differ'
    )

    directory: StringProperty(
        name='Output Directory',
        description='Directory in which to write one .psa file per armature',
        subtype='DIR_PATH',
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # Gather (action, invert_root_rotation) pairs per armature across
        # every selected link, and remember which exported name (the
        # link's name) each action should carry.
        entries_by_armature = {}
        export_names_by_action_name = {}

        for link in context.scene.psa_action_links:
            if not link.is_selected:
                continue
            for entry in link.entries:
                if entry.armature is None or entry.action is None:
                    self.report({'WARNING'}, f'Skipping incomplete entry in link "{link.name}"')
                    continue

                entries_by_armature.setdefault(entry.armature, [])
                pair = (entry.action, entry.invert_root_rotation)
                if pair not in entries_by_armature[entry.armature]:
                    entries_by_armature[entry.armature].append(pair)

                existing = export_names_by_action_name.get(entry.action.name)
                if existing is not None and existing != link.name:
                    self.report(
                        {'WARNING'},
                        f'Action "{entry.action.name}" is used in both "{existing}" and '
                        f'"{link.name}"; exporting it as "{link.name}"'
                    )
                export_names_by_action_name[entry.action.name] = link.name

        if len(entries_by_armature) == 0:
            self.report({'ERROR_INVALID_CONTEXT'}, 'No linked actions were selected for export.')
            return {'CANCELLED'}

        if not self.directory:
            self.report({'ERROR_INVALID_CONTEXT'}, 'No output directory was chosen.')
            return {'CANCELLED'}

        previous_active = context.view_layer.objects.active
        exported_files = []

        try:
            for armature, action_pairs in entries_by_armature.items():
                context.view_layer.objects.active = armature

                # Actions that need the root flipped can't share a single
                # build() call with ones that don't, since the flag applies
                # to the whole call. Build each group separately, then
                # merge the results into one Psa for this armature.
                actions_by_invert_flag = {False: [], True: []}
                for action, invert_flag in action_pairs:
                    actions_by_invert_flag[invert_flag].append(action)

                merged_psa = None
                for invert_flag, actions in actions_by_invert_flag.items():
                    if len(actions) == 0:
                        continue

                    options = PsaBuilderOptions()
                    options.actions = actions
                    options.should_invert_root_rotation = invert_flag

                    builder = PsaBuilder()
                    psa = builder.build(context, options)
                    merged_psa = _merge_psa(merged_psa, psa)

                if merged_psa is None:
                    continue

                # Relabel each sequence with its link name. ctypes truncates
                # c_char array fields at the first NUL on read, so this is
                # already the clean action name the builder set it to.
                for sequence in merged_psa.sequences:
                    original_name = sequence.name.decode('utf-8')
                    override_name = export_names_by_action_name.get(original_name)
                    if override_name is not None:
                        sequence.name = bytes(override_name, encoding='utf-8')

                filepath = os.path.join(self.directory, f'{armature.name}.psa')
                exporter = PsaExporter(merged_psa)
                exporter.export(filepath)
                exported_files.append(filepath)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        finally:
            context.view_layer.objects.active = previous_active

        names = ', '.join(os.path.basename(f) for f in exported_files)
        self.report({'INFO'}, f'Exported {len(exported_files)} file(s): {names}')
        return {'FINISHED'}


classes = [
    PsaActionLinkEntry,
    PsaActionLink,
    PSA_UL_ActionLinkList,
    PSA_UL_ActionLinkEntryList,
    PSA_OT_action_link_add,
    PSA_OT_action_link_remove,
    PSA_OT_action_link_duplicate,
    PSA_OT_action_link_apply,
    PSA_OT_action_link_entry_add,
    PSA_OT_action_link_entry_remove,
    PSA_OT_export_linked,
    PSA_PT_action_linker,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.psa_action_links = CollectionProperty(type=PsaActionLink)
    bpy.types.Scene.psa_action_links_index = IntProperty(default=0)


def unregister():
    del bpy.types.Scene.psa_action_links_index
    del bpy.types.Scene.psa_action_links
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
