"""
landscape_pilot: bench + tree の風景シーンをheadless Blenderで組み立て、
ワールド設定・レンダリング・コンポジットまで一括実行する。
GitHub Actions上での実行を想定(--background --python このファイル)。

入力: $GITHUB_WORKSPACE/assets/bench.glb, $GITHUB_WORKSPACE/assets/tree.glb
出力: $GITHUB_WORKSPACE/output/render.png, $GITHUB_WORKSPACE/output/scene.blend
"""
import bpy
import math
import os

WORKSPACE = os.environ.get("GITHUB_WORKSPACE", os.getcwd())
ASSET_DIR = os.path.join(WORKSPACE, "assets")
OUTPUT_DIR = os.path.join(WORKSPACE, "output")
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
background = wnt.nodes.new("ShaderNodeBackground")
# Nishitaは物理輝度が強すぎて露出制御が難しいため、手動グラデーションの空にする
# (色と明るさを直接指定でき、露出を完全にコントロールできる)
tex_coord = wnt.nodes.new("ShaderNodeTexCoord")
sep_xyz = wnt.nodes.new("ShaderNodeSeparateXYZ")
sky_ramp = wnt.nodes.new("ShaderNodeValToRGB")
sky_ramp.color_ramp.elements[0].position = 0.0
sky_ramp.color_ramp.elements[0].color = (0.75, 0.80, 0.82, 1.0)  # 地平線付近(白っぽい水色)
sky_ramp.color_ramp.elements[1].position = 1.0
sky_ramp.color_ramp.elements[1].color = (0.30, 0.48, 0.70, 1.0)  # 天頂(濃い青)
background.inputs["Strength"].default_value = 1.0

wnt.links.new(tex_coord.outputs["Generated"], sep_xyz.inputs["Vector"])
wnt.links.new(sep_xyz.outputs["Z"], sky_ramp.inputs["Fac"])
wnt.links.new(sky_ramp.outputs["Color"], background.inputs["Color"])
wnt.links.new(background.outputs["Background"], w_out.inputs["Surface"])

bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
sun = bpy.context.active_object
sun.name = "Sun"
sun.data.energy = 3.0
sun.data.angle = math.radians(1.5)
# 元画像: 光源は右奥やや低い高度、影は左手前に伸びる
sun.rotation_euler = (
    math.radians(90) - math.radians(20),  # 仰角20°
    0,
    math.radians(250),  # 方位角(右奥方向)
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
color_balance.correction_method = "LIFT_GAMMA_GAIN"
color_balance.gain = (1.02, 1.0, 0.97)
glare = ctree.nodes.new("CompositorNodeGlare")
glare.glare_type = "FOG_GLOW"
glare.threshold = 1.0
glare.mix = -0.3
vignette_mix = ctree.nodes.new("CompositorNodeMixRGB")
vignette_mix.blend_type = "MULTIPLY"
vignette_mix.inputs[0].default_value = 0.25
ellipse = ctree.nodes.new("CompositorNodeEllipseMask")
ellipse.width = 0.9
ellipse.height = 0.9
ellipse_blur = ctree.nodes.new("CompositorNodeBlur")
ellipse_blur.size_x = 60
ellipse_blur.size_y = 60
composite = ctree.nodes.new("CompositorNodeComposite")

ctree.links.new(rlayers.outputs["Image"], color_balance.inputs["Image"])
ctree.links.new(color_balance.outputs["Image"], glare.inputs["Image"])
ctree.links.new(glare.outputs["Image"], vignette_mix.inputs[1])
ctree.links.new(ellipse.outputs["Mask"], ellipse_blur.inputs["Image"])
ctree.links.new(ellipse_blur.outputs["Image"], vignette_mix.inputs[2])
ctree.links.new(vignette_mix.outputs["Image"], composite.inputs["Image"])

# ---------------------------------------------------------------
# 7. 出力
# ---------------------------------------------------------------
scene.render.filepath = os.path.join(OUTPUT_DIR, "render.png")
scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTPUT_DIR, "scene.blend"))

print("DONE: render written to", scene.render.filepath)
