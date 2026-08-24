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


def strip_thin_base_slab(obj, thickness_ratio=0.06, footprint_ratio=0.5, max_pieces=20):
    """objの中に、全高に比べて極端に薄く水平方向には広い"台座/影受け板"らしき
    ルーズパーツがあれば削除する(Meshyのimage-to-3dが単体撮影時の接地シャドウを
    そのまま平板ジオメトリとして焼き込むことがあるため)。
    パーツ数が多すぎる場合(有機物の枝葉など個々が小さいパーツに分かれている場合)
    は誤検出のリスクが高いため何もせず1つに結合し直すだけにする。"""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    pieces = [o for o in bpy.context.selected_objects if o.type == "MESH"]

    def rejoin(objs):
        bpy.ops.object.select_all(action="DESELECT")
        for p in objs:
            p.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        if len(objs) > 1:
            bpy.ops.object.join()
        return bpy.context.view_layer.objects.active

    if len(pieces) <= 1 or len(pieces) > max_pieces:
        return rejoin(pieces)

    stats = []
    for p in pieces:
        xs = [v.co.x for v in p.data.vertices]
        ys = [v.co.y for v in p.data.vertices]
        zs = [v.co.z for v in p.data.vertices]
        stats.append((p, max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))

    total_z = max(s[3] for s in stats)
    total_footprint = max(max(s[1], s[2]) for s in stats)

    keep = []
    for p, dx, dy, dz in stats:
        thin = total_z > 0 and (dz / total_z) < thickness_ratio
        wide = total_footprint > 0 and (max(dx, dy) / total_footprint) > footprint_ratio
        if thin and wide:
            print(f"[cleanup] {obj.name}: removing thin base slab piece (dz={dz:.4f}, footprint={max(dx, dy):.4f})")
            bpy.data.objects.remove(p, do_unlink=True)
        else:
            keep.append(p)

    if not keep:
        keep = pieces  # 誤検出で全部消えるのを防ぐ安全策(通常は起きない)

    return rejoin(keep)


def import_glb_scaled(filepath, target_height_m, name, strip_thin_base=False):
    """glbをインポートし、バウンディングボックス高さがtarget_height_mになるよう
    一様スケールし、原点を底面中心に揃えて1つのオブジェクトにjoinして返す"""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=filepath)
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"{filepath}: メッシュが見つかりません")

    # glTFインポートは軸変換用の親Empty(独自scale/rotationを持つ場合がある)を
    # 作ることがある。親のtransformを子に焼き込んでから外し、その後obj.scaleを
    # 1.0基準にtransform_applyしておかないと、後段の「measured_height→scale上書き」
    # 計算が親のscaleぶんだけズレて接地位置がズレる(地面に埋まる/浮く原因)。
    for o in imported:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")

    for o in bpy.context.selected_objects:
        if o.type != "MESH":
            o.select_set(False)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name

    if strip_thin_base:
        obj = strip_thin_base_slab(obj)
        obj.name = name

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    assert tuple(round(s, 4) for s in obj.scale) == (1.0, 1.0, 1.0), obj.scale

    # ここでobj.scaleは確実に(1,1,1)なので、以降のスケール計算は安全
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_z = min(v.z for v in verts)
    max_z = max(v.z for v in verts)
    height = max(max_z - min_z, 1e-6)
    scale = target_height_m / height
    obj.scale = (scale, scale, scale)
    bpy.context.view_layer.update()

    # 底面中心を原点(0,0,0)に揃える
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_z = min(v.z for v in verts)
    center_x = sum(v.x for v in verts) / len(verts)
    center_y = sum(v.y for v in verts) / len(verts)
    obj.location.x -= center_x
    obj.location.y -= center_y
    obj.location.z -= min_z
    bpy.context.view_layer.update()

    # 自己検証: 配置後の接地点がZ=0付近(浮き/埋まりなし)か数値でログに残す
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    final_min_z = min(v.z for v in verts)
    final_max_z = max(v.z for v in verts)
    print(
        f"[check] {name}: min_z={final_min_z:.4f} max_z={final_max_z:.4f} "
        f"height={final_max_z - final_min_z:.4f} (target={target_height_m})"
    )
    if abs(final_min_z) > 0.02:
        print(f"[WARNING] {name} may be floating/sunk: min_z={final_min_z:.4f} (expected ~0)")

    return obj


# ---------------------------------------------------------------
# 1. 被写体の配置(scene_analysis.mdの見積もりに基づく)
# ---------------------------------------------------------------
# ベンチ: 前景・カメラから約5m・全長1.6m
bench = import_glb_scaled(os.path.join(ASSET_DIR, "bench.glb"), target_height_m=0.9, name="Bench", strip_thin_base=True)
bench.location = (-2.2, 5.0, 0.0)
bench.rotation_euler = (0, 0, math.radians(20))

# 木: 中景・カメラから約20m(ベンチの4倍)・樹高8m
tree = import_glb_scaled(os.path.join(ASSET_DIR, "tree.glb"), target_height_m=8.0, name="Tree")
tree.location = (5.5, 20.0, 0.0)

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
cam.rotation_euler = (math.radians(80), 0, 0)
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
composite = ctree.nodes.new("CompositorNodeComposite")

ctree.links.new(rlayers.outputs["Image"], color_balance.inputs["Image"])
ctree.links.new(color_balance.outputs["Image"], glare.inputs["Image"])
ctree.links.new(glare.outputs["Image"], composite.inputs["Image"])

# ---------------------------------------------------------------
# 7. 出力
# ---------------------------------------------------------------
scene.render.filepath = os.path.join(OUTPUT_DIR, "render.png")
scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTPUT_DIR, "scene.blend"))

print("DONE: render written to", scene.render.filepath)
