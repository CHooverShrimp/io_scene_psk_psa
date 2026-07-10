This Blender add-on allows you to export meshes and animations to the [PSK and PSA file formats](https://wiki.beyondunreal.com/PSK_%26_PSA_file_formats).

# Installation
1. Download the zip file for the latest version from the [releases](https://github.com/DarklightGames/io_export_psk_psa/releases) page.
2. Open Blender 2.80 or later.
3. Navigate to the Blender Preferences (Edit > Preferences).
4. Select the "Add-ons" tab.
5. Click the "Install..." button.
6. Select the .zip file that you downloaded earlier and click "Install Add-on".
7. Enable the newly added "Import-Export: PSK/PSA Exporter" addon.

# Usage
## Exporting a PSK
1. Select the mesh objects you wish to export.
3. Navigate to File > Export > Unreal PSK (.psk)
4. Enter the file name and click "Export".

## Exporting a PSA
1. Select the armature objects you wish to export.
2. Navigate to File > Export > Unreal PSA (.psa)
3. Enter the file name and click "Export".

# FAQ
## Can I use this addon to import PSK and PSA files?
Currently, no.

Presumably you are using this in concert with the [UE Viewer](https://www.gildor.org/en/projects/umodel) program to import extracted meshes. It is *not recommended* to export PSK/PSA from UE Viewer since it [does not preserve smoothing groups](https://github.com/gildor2/UEViewer/issues/235). As a result, the shading of imported models will be incorrect and will need to be manually fixed. Instead, it is recommended to export meshes to the glTF format for import into Blender since it preserves the correct mesh shading.

Regardless, if you are dead set on using a PSK/PSA importer, use [this one](https://github.com/Befzz/blender3d_import_psk_psa).

# Hoover's changes:
## Implemented an animation linker-exporter system for Rising Storm 2 3rd-person animations.
<img width="935" height="634" alt="image" src="https://github.com/user-attachments/assets/e8c383d7-f6b7-4a38-824a-bdf4d02fd0d5" />

In RS2, the characters (CHR) and the weapons (WP) are exported independently as two different animsets, but the animation are often co-dependent when animated. Example, to animate `Bayonet_Attach`, one would have to animate the character and the weapon independently. But the animator may use constraints such as `Child-of` to ease in the process, which will break when exporting normally with the plugin, who sequentally exports all animation from the list without prejudice for its co-dependent animations. In order to properly export, each animation must be exported with its partner's animation selected to inherit the partner's animations.

Secondly, in RS2, the naming convention between the CHR and WP are identical. This would be impossible to do in Blender. This plugin will export the action with proper name attributed by the name of its group.

The plugin will export the animset as n numbers of .psa, depending on how many armatures in each link group.
