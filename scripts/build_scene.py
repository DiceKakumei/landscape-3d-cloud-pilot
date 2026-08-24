"""
landscape_pilot: bench + tree の風景シーンをheadless Blenderで組み立て、
ワールド設定・レンダリング・コンポジットまで一括実行する。
GitHub Actions上での実行を想定(--background --python このファイル)。

入力: /github/workspace/assets/bench.glb, /github/workspace/assets/tree.glb
出力: /github/workspace/output/render.png, /github/workspace/output/scene.blend
"""
import bpy
import math
import os

ASSET_DIR = "/github/workspace/assets"
OUTPUT_DIR = "/github/workspace/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------
# 0. デフォルトシーンのクリア
# ---------------------------------------------------------------
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for block in list(bpy.data.meshes):
    if block.users == 0:
        bpy.data.meshes.remove(block)

scene = bpy.context.scene
scene.unit_settings.system = "METRIC"


def import_glb_scaled(filepath, target_height_m, name):
    """glbをインポートし、バウンディングボックス高さがtarget_height_mになるよう
    一様スケールし、原点を底面中心に揃えて1つのオブジェクトにjoinして返す"""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=filepath)
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"{filepath}: メッシュが見つかりません")

    for o in imported:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name

    # バウンディングボックスから高さ(Z)を測り、目標高さにスケール
    bbox = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_z = min(v.z for v in bbox)
    max_z = max(v.z for v in bbox)
    height = max(max_z - min_z, 1e-6)
    scale = target_height_m / height
    obj.scale = (scale, scale, scale)
    bpy.context.view_layer.update()

    # 底面中心を原点(0,0,0)に揃える
    bbox = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_z = min(v.z for v in bbox)
    center_x = sum(v.x for v in bbox) / len(bbox)
    center_y = sum(v.y for v in bbox) / len(bbox)
    obj.location.x -= center_x
    obj.location.y -= center_y
    obj.location.z -= min_z
    return obj


# ---------------------------------------------------------------
# 1. 被写体の配置(scene_analysis.mdの見積もりに基づく)
# ---------------------------------------------------------------
# ベンチ: 前景・カメラから約8m・全長1.6m
bench = import_glb_scaled(os.path.join(ASSET_DIR, "bench.glb"), target_height_m=0.9, name="Bench")
bench.location = (-3.0, 8.0, 0.0)
bench.rotation_euler = (0, 0, math.radians(20))

# 木: 中景・カメラから約32m(ベンチの4倍)・樹高8m
tree = import_glb_scaled(os.path.join(ASSET_DIR, "tree.glb"), target_height_m=8.0, name="Tree")
tree.location = (6.5, 32.0, 0.0)

# ---------------------------------------------------------------
# 2. 地面(平坦な芝生プレーン)
# ---------------------------------------------------------------
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Ground"

grass_mat = bpy.data.materials.new("Grass")
grass_mat.use_nodes = True
nt = grass_mat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
noise = nt.nodes.new("ShaderNodeTexNoise")
ramp = nt.nodes.new("ShaderNodeValToRGB")
mapping = nt.nodes.new("ShaderNodeMapping")
coord = nt.nodes.new("ShaderNodeTexCoord")

noise.inputs["Scale"].default_value = 40.0
ramp.color_ramp.elements[0].color = (0.16, 0.30, 0.09, 1.0)
ramp.color_ramp.elements[1].color = (0.30, 0.42, 0.16, 1.0)
bsdf.inputs["Roughness"].default_value = 0.9

nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
ground.data.materials.append(grass_mat)

# ---------------------------------------------------------------
# 3. ワールド(空)・太陽光
#    元画像: 水平線は画面上から約60%、光源は右奥やや低い高度、影は左手前に伸びる
# ---------------------------------------------------------------
world = bpy.data.worlds.new("Sky")
scene.world = world
world.use_nodes = True
wnt = world.node_tree
wnt.nodes.clear()
w_out = wnt.nodes.new("ShaderNodeOutputWorld")
sky_tex = wnt.nodes.new("ShaderNodeTexSky")
sky_tex.sky_type = "NISHITA"
sky_tex.sun_elevation = math.radians(20)
sky_tex.sun_rotation = math.radians(250)  # 右奥方向
sky_tex.sun_intensity = 1.0
wnt.links.new(sky_tex.outputs["Color"], w_out.inputs["Surface"])

bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
sun = bpy.context.active_object
sun.name = "Sun"
sun.data.energy = 3.0
sun.data.angle = math.radians(1.5)
# sun_elevationはXY平面からの仰角、sun_rotationはZ軸まわりの方位角に対応させる
sun.rotation_euler = (
    math.radians(90) - math.radians(20),
    0,
    math.radians(250),
)

# ---------------------------------------------------------------
# 4. カメラ(元画像の水平線位置・目線の高さを再現)
# ---------------------------------------------------------------
bpy.ops.object.camera_add(location=(0, -1.0, 1.6))
cam = bpy.context.active_object
cam.name = "MainCamera"
cam.rotation_euler = (math.radians(88), 0, 0)
cam.data.lens = 35
scene.camera = cam

# ---------------------------------------------------------------
# 5. レンダリング設定(Cycles・CPU・デノイズ)
# ---------------------------------------------------------------
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 64
scene.cycles.use_denoising = True
scene.cycles.adaptive_threshold = 0.05
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.film_transparent = False

# ---------------------------------------------------------------
# 6. コンポジット(色調補正・グレア・ビネット)
# ---------------------------------------------------------------
scene.use_nodes = True
ctree = scene.node_tree
ctree.nodes.clear()
rlayers = ctree.nodes.new("CompositorNodeRLayers")
color_balance = ctree.nodes.new("CompositorNodeColorBalance")
color_balance.color_balance.gain = (1.02, 1.0, 0.97)
glare = ctree.nodes.new("CompositorNodeGlare")
glare.glare_type = "FOG_GLOW"
glare.threshold = 1.0
glare.mix = -0.3
vignette_mix = ctree.nodes.new("CompositorNodeMixRGB")
vignette_mix.blend_type = "MULTIPLY"
vignette_mix.inputs[0].default_value = 0.25
ellipse = ctree.nodes.new("CompositorNodeEllipseMask")
ellipse.width = 0.85
ellipse.height = 0.85
composite = ctree.nodes.new("CompositorNodeComposite")

ctree.links.new(rlayers.outputs["Image"], color_balance.inputs["Image"])
ctree.links.new(color_balance.outputs["Image"], glare.inputs["Image"])
ctree.links.new(glare.outputs["Image"], vignette_mix.inputs[1])
ctree.links.new(ellipse.outputs["Mask"], vignette_mix.inputs[2])
ctree.links.new(vignette_mix.outputs["Image"], composite.inputs["Image"])

# ---------------------------------------------------------------
# 7. 出力
# ---------------------------------------------------------------
scene.render.filepath = os.path.join(OUTPUT_DIR, "render.png")
scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTPUT_DIR, "scene.blend"))

print("DONE: render written to", scene.render.filepath)
