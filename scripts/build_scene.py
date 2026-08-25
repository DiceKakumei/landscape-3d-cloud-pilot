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


def build_bench(length=1.6, depth=0.5, seat_height=0.4, total_height=0.9, name="Bench"):
    """Meshyのimage-to-3dは脚の間の空間を閉じたメッシュにするため厚い板で
    埋めてしまう(bench2.glbで実測確認済み: 底面から高さ30%までのX-Z footprint
    がほぼ全体footprintと一致=脚の間が中空でなく塗りつぶされている)。
    ベンチのような単純な直方体の組み合わせで表現できる人工物は、
    最初のscene_analysis.mdの方針通りbpyプリミティブで直接組み立てる。"""
    leg_thickness = 0.08
    plank_thickness = 0.045
    inset = 0.12
    leg_x = length / 2 - inset
    leg_y = depth / 2 - leg_thickness / 2 - 0.02

    parts = []

    def add_box(dims, location):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        b = bpy.context.active_object
        b.scale = dims
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        parts.append(b)
        return b

    for sx in (-1, 1):
        add_box((leg_thickness, leg_thickness, seat_height), (sx * leg_x, leg_y, seat_height / 2))
        add_box((leg_thickness, leg_thickness, total_height), (sx * leg_x, -leg_y, total_height / 2))

    seat_board_depth = (depth - 0.04) / 2
    seat_board_length = length - 2 * inset * 0.3
    for sy in (-1, 1):
        add_box(
            (seat_board_length, seat_board_depth, plank_thickness),
            (0, sy * (seat_board_depth / 2 + 0.02), seat_height - plank_thickness / 2),
        )

    back_y = -leg_y
    back_bottom = seat_height + 0.08
    slat_gap = 0.03
    slat_h = (total_height - back_bottom - 2 * slat_gap) / 3
    for i in range(3):
        z = back_bottom + i * (slat_h + slat_gap) + slat_h / 2
        add_box((seat_board_length, plank_thickness, slat_h), (0, back_y, z))

    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name

    # joinされたオブジェクトの原点を接地中心(0,0,0)に揃え直す
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")

    mat = bpy.data.materials.new(f"{name}_wood")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.30, 0.20, 0.12, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.9  # 座面だけ光沢で白飛びして見えるのを抑える
    obj.data.materials.append(mat)

    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    print(f"[check] {name}: min_z={min(v.z for v in verts):.4f} max_z={max(v.z for v in verts):.4f}")
    return obj


def import_glb_scaled(filepath, target_height_m, name):
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
# 注意: import_glb_scaled/build_bench は内部でオブジェクト原点を「接地面の中心(0,0,0)」に
# 揃えている。ここで location をまるごと上書きすると、その補正量(特にZ)が消えて
# 地面にめり込む/浮くバグになるため、必ず加算(+=)で配置すること。
bench = build_bench(length=1.6, depth=0.5, seat_height=0.4, total_height=0.9, name="Bench")
bench.location.x += -1.6
bench.location.y += 4.0
bench.rotation_euler = (0, 0, math.radians(20))

# 木: 中景・カメラから約14m(ベンチの3.5倍)・樹高8m
# (ベンチと木の間の空きスペースが広すぎたため、両者を少し中央寄りに詰めた)
tree = import_glb_scaled(os.path.join(ASSET_DIR, "tree.glb"), target_height_m=8.0, name="Tree")
tree.location.x += 3.2
tree.location.y += 14.0
bpy.context.view_layer.update()

# ---------------------------------------------------------------
# 2. 地面(平坦な芝生プレーン)
# ---------------------------------------------------------------
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Ground"

# 法線バンプだけでは近距離(ベンチ周辺)がのっぺりして見えるため、
# 実ジオメトリの緩やかな起伏をDisplaceモディファイアで加える
bpy.context.view_layer.objects.active = ground
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.subdivide(number_cuts=150)
bpy.ops.object.mode_set(mode="OBJECT")

terrain_tex = bpy.data.textures.new("TerrainNoise", type="CLOUDS")
terrain_tex.noise_scale = 6.0
terrain_tex.noise_depth = 2
disp_mod = ground.modifiers.new("Terrain", type="DISPLACE")
disp_mod.texture = terrain_tex
disp_mod.strength = 0.06
disp_mod.mid_level = 0.5

grass_mat = bpy.data.materials.new("Grass")
grass_mat.use_nodes = True
nt = grass_mat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
mapping = nt.nodes.new("ShaderNodeMapping")
coord = nt.nodes.new("ShaderNodeTexCoord")

# 大きい班(パッチ状のムラ)+ 細かいノイズ(芝の質感)を重ねて、のっぺり感をなくす
# (1回目の調整では効果が弱すぎたため、スケール・コントラストとも大きく強めた)
patch_noise = nt.nodes.new("ShaderNodeTexNoise")
patch_noise.inputs["Scale"].default_value = 2.5
patch_noise.inputs["Detail"].default_value = 4.0
patch_ramp = nt.nodes.new("ShaderNodeValToRGB")
patch_ramp.color_ramp.elements[0].color = (0.10, 0.22, 0.05, 1.0)
patch_ramp.color_ramp.elements[1].color = (0.38, 0.50, 0.20, 1.0)

fine_noise = nt.nodes.new("ShaderNodeTexNoise")
fine_noise.inputs["Scale"].default_value = 150.0
fine_noise.inputs["Detail"].default_value = 8.0

mix_color = nt.nodes.new("ShaderNodeMixRGB")
mix_color.blend_type = "MULTIPLY"
mix_color.inputs["Fac"].default_value = 0.5

bump = nt.nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.3

bsdf.inputs["Roughness"].default_value = 0.85

nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
nt.links.new(mapping.outputs["Vector"], patch_noise.inputs["Vector"])
nt.links.new(mapping.outputs["Vector"], fine_noise.inputs["Vector"])
nt.links.new(patch_noise.outputs["Fac"], patch_ramp.inputs["Fac"])
nt.links.new(patch_ramp.outputs["Color"], mix_color.inputs["Color1"])
nt.links.new(fine_noise.outputs["Color"], mix_color.inputs["Color2"])
nt.links.new(fine_noise.outputs["Fac"], bump.inputs["Height"])
nt.links.new(mix_color.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
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
sky_ramp.color_ramp.elements[0].color = (0.80, 0.79, 0.76, 1.0)  # 地平線付近(白っぽい暖色)
sky_ramp.color_ramp.elements.new(0.35)
sky_ramp.color_ramp.elements[1].color = (0.72, 0.79, 0.83, 1.0)  # 中間(薄い水色)
sky_ramp.color_ramp.elements[2].position = 1.0
sky_ramp.color_ramp.elements[2].color = (0.30, 0.48, 0.70, 1.0)  # 天頂(濃い青)
background.inputs["Strength"].default_value = 1.0

# 雲のような薄いムラを空全体に重ねる(1回目の調整では効果が弱すぎたため強めた)
cloud_noise = wnt.nodes.new("ShaderNodeTexNoise")
cloud_noise.inputs["Scale"].default_value = 1.2
cloud_noise.inputs["Detail"].default_value = 8.0
cloud_ramp = wnt.nodes.new("ShaderNodeValToRGB")
cloud_ramp.color_ramp.elements[0].position = 0.30
cloud_ramp.color_ramp.elements[0].color = (0.05, 0.06, 0.08, 1)
cloud_ramp.color_ramp.elements[1].position = 0.55
cloud_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)
cloud_mix = wnt.nodes.new("ShaderNodeMixRGB")
cloud_mix.blend_type = "MIX"
cloud_mix.inputs["Fac"].default_value = 0.6

wnt.links.new(tex_coord.outputs["Generated"], sep_xyz.inputs["Vector"])
wnt.links.new(sep_xyz.outputs["Z"], sky_ramp.inputs["Fac"])
wnt.links.new(tex_coord.outputs["Generated"], cloud_noise.inputs["Vector"])
wnt.links.new(cloud_noise.outputs["Fac"], cloud_ramp.inputs["Fac"])
wnt.links.new(sky_ramp.outputs["Color"], cloud_mix.inputs["Color1"])
wnt.links.new(cloud_ramp.outputs["Color"], cloud_mix.inputs["Color2"])
wnt.links.new(cloud_mix.outputs["Color"], background.inputs["Color"])
wnt.links.new(background.outputs["Background"], w_out.inputs["Surface"])

# 地平線が定規で引いたようにシャープすぎるとの指摘に対応: 大気遠近(かすみ)を
# Mistパスで再現し、コンポジット側で遠景に空の色を薄く混ぜる
world.mist_settings.start = 10.0
world.mist_settings.depth = 15.0
world.mist_settings.falloff = "QUADRATIC"
# depthを短くして早めにFac=1.0で頭打ちにする: 広角レンズでは画面端ほど同じ行でも
# 実距離が長くなるため、頭打ちにする前(遷移帯)が広いと水平線が弓なりに歪んで見える
bpy.context.view_layer.use_pass_mist = True

bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
sun = bpy.context.active_object
sun.name = "Sun"
sun.data.energy = 3.0
sun.data.angle = math.radians(10.0)  # 影のエッジを柔らかくする(4度でもまだ硬いとの指摘のため増加)
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
# 木(高さ8m、距離約15m)が画角上端で見切れないよう、
# レンズを広角にし下向きの角度を弱めて画角の上側に余裕を持たせる
cam.rotation_euler = (math.radians(85), 0, 0)
cam.data.lens = 18
scene.camera = cam

# ---------------------------------------------------------------
# 5. レンダリング設定(Cycles・CPU・デノイズ)
# ---------------------------------------------------------------
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 256
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

# 大気遠近: Mistパスを使って遠景ほど空の色(かすみ)を混ぜ、地平線の硬さを和らげる
# (Mistの遷移帯を広角カメラのまま強く使うと、画面端ほど同じ行でも実距離が
# 長くなる影響で水平線が弓なりに見えてしまったため、最大強度を大きく絞って
# 「ほんのり滲む」程度に抑える)
haze_mix = ctree.nodes.new("CompositorNodeMixRGB")
haze_mix.blend_type = "MIX"
haze_mix.inputs[2].default_value = (0.80, 0.79, 0.76, 1.0)
haze_scale = ctree.nodes.new("CompositorNodeMath")
haze_scale.operation = "MULTIPLY"
haze_scale.inputs[1].default_value = 0.3

# イラスト調スタイライズ: 彩度を上げてから、
# 1) Kuwaharaフィルタで絵の具の面のような塗り分けにする(細部のノイズを消す)
# 2) Posterizeで色数を落として平坦な塗りにする
# 3) Sobelエッジ検出で輪郭線を作り、線画として乗算で重ねる
hue_sat = ctree.nodes.new("CompositorNodeHueSat")
hue_sat.inputs["Saturation"].default_value = 1.35

kuwahara = ctree.nodes.new("CompositorNodeKuwahara")
kuwahara.variant = "CLASSIC"
kuwahara.size = 8

posterize = ctree.nodes.new("CompositorNodePosterize")
posterize.inputs["Steps"].default_value = 7

edge_sobel = ctree.nodes.new("CompositorNodeFilter")
edge_sobel.filter_type = "SOBEL"
edge_bw = ctree.nodes.new("CompositorNodeRGBToBW")
edge_strength = ctree.nodes.new("CompositorNodeMath")
edge_strength.operation = "MULTIPLY"
edge_strength.inputs[1].default_value = 3.0
edge_clamp = ctree.nodes.new("CompositorNodeMath")
edge_clamp.operation = "MINIMUM"
edge_clamp.inputs[1].default_value = 1.0
edge_invert = ctree.nodes.new("CompositorNodeMath")
edge_invert.operation = "SUBTRACT"
edge_invert.use_clamp = True
edge_invert.inputs[0].default_value = 1.0

line_mix = ctree.nodes.new("CompositorNodeMixRGB")
line_mix.blend_type = "MULTIPLY"
line_mix.inputs[0].default_value = 1.0

composite = ctree.nodes.new("CompositorNodeComposite")

ctree.links.new(rlayers.outputs["Image"], color_balance.inputs["Image"])
ctree.links.new(color_balance.outputs["Image"], glare.inputs["Image"])
ctree.links.new(glare.outputs["Image"], haze_mix.inputs[1])
ctree.links.new(rlayers.outputs["Mist"], haze_scale.inputs[0])
ctree.links.new(haze_scale.outputs["Value"], haze_mix.inputs[0])

ctree.links.new(haze_mix.outputs["Image"], hue_sat.inputs["Image"])
# 輪郭線は塗りつぶし前(Kuwahara/Posterizeで滲む前)のシャープな段階から検出する
ctree.links.new(hue_sat.outputs["Image"], edge_sobel.inputs["Image"])
ctree.links.new(edge_sobel.outputs["Image"], edge_bw.inputs["Image"])
ctree.links.new(edge_bw.outputs["Val"], edge_strength.inputs[0])
ctree.links.new(edge_strength.outputs["Value"], edge_clamp.inputs[0])
ctree.links.new(edge_clamp.outputs["Value"], edge_invert.inputs[1])

ctree.links.new(hue_sat.outputs["Image"], kuwahara.inputs["Image"])
ctree.links.new(kuwahara.outputs["Image"], posterize.inputs["Image"])
ctree.links.new(posterize.outputs["Image"], line_mix.inputs[1])
ctree.links.new(edge_invert.outputs["Value"], line_mix.inputs[2])
ctree.links.new(line_mix.outputs["Image"], composite.inputs["Image"])

# ---------------------------------------------------------------
# 7. 出力
# ---------------------------------------------------------------
scene.render.filepath = os.path.join(OUTPUT_DIR, "render.png")
scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTPUT_DIR, "scene.blend"))

print("DONE: render written to", scene.render.filepath)
