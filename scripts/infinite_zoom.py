# 無限ズーム絵：絵の一部に次の絵が入れ子になっていて、延々ズームし続けるループ動画（Blender 5.0 headless）
# blender --background --python scripts/infinite_zoom.py -- <フレーム出力dir> [step]
#   step: 何フレームおきに描くか（既定1=全フレーム。24の約数。確認用は24）
# 仕組み：実際に無限に小さい物は置かない（float精度が足りない）。毎フレーム「今いる絵」を幅1に置き直し、
#   その先 DEPTH 段だけを縮小して並べる。カメラは正投影で、次の絵の位置へ指数的に寄る。
import colorsys
import math
import os
import random
import sys

import bmesh
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir = os.path.abspath(argv[0])
STEP = int(argv[1]) if len(argv) > 1 else 1

N = 6                # 絵の枚数（DEPTH以上）。最後の絵の中に最初の絵が入るので動画がループする
S = 1 / 12           # 1段ごとの縮小率
SEC_PER_LEVEL = 2.0
FPS = 24
ASPECT = 16 / 9      # 縦長。各絵は「幅1 x 高さASPECT」の枠（原点中心）に描く
DEPTH = 4            # 同時に置く段数（4段目は1px未満なので出現が見えない）
BACK_R = 1.05        # 絵の下地の円の半径。枠の対角の半分(1.02)より大きく＝寄り切ると画面を覆う


def cam(anchor, u):
    """絵の中の anchor へ u(0→1) だけ寄ったときのカメラ中心と表示幅。"""
    k = S ** u
    f = (1 - k) / (1 - S)
    return anchor[0] * f, anchor[1] * f, k


# 継ぎ目の条件：寄り切った画面 = 次の絵の枠ちょうど
assert all(math.isclose(a, b) for a, b in zip(cam((0.2, -0.1), 1.0), (0.2, -0.1, S)))
assert N >= DEPTH

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def mat(h, s, v):
    rgb = [c ** 2.2 for c in colorsys.hsv_to_rgb(h, s, v)]  # sRGB→リニア
    m = bpy.data.materials.new("flat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*rgb, 1)
    nt.links.new(e.outputs[0], nt.nodes.new("ShaderNodeOutputMaterial").inputs[0])
    return m


def add(parent, data, xy, z, material):
    ob = bpy.data.objects.new(data.name, data)
    ob.location = (xy[0], xy[1], z)
    ob.parent = parent
    data.materials.append(material)
    sc.collection.objects.link(ob)


def disc(r):
    mesh = bpy.data.meshes.new("disc")
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=256, radius=r)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


# --- 絵（確認用の仮の絵：下地の円＋大きな円＋粒＋番号。本番はここを差し替える）---
random.seed(1)
roots, anchors = [], []
for j in range(N):
    h = j / N
    root = bpy.data.objects.new(f"level{j}", None)
    sc.collection.objects.link(root)
    ang = math.radians(-90 + random.uniform(-50, 50))
    anchor = (0.2 * math.cos(ang), 0.2 * math.sin(ang))  # 次の絵が入る場所
    add(root, disc(BACK_R), (0, 0), 0, mat(h, 0.2, 1.0))
    add(root, disc(0.38), (0, 0), 0.001, mat(h, 0.65, 0.9))
    dots = 0
    while dots < 7:
        a, r = random.uniform(0, math.tau), random.uniform(0.08, 0.32)
        p = (r * math.cos(a), r * math.sin(a))
        if math.dist(p, anchor) > 0.14 and math.dist(p, (0, 0.14)) > 0.17:
            add(root, disc(random.uniform(0.015, 0.04)), p, 0.002, mat(h, 0.8, 0.65))
            dots += 1
    txt = bpy.data.curves.new("num", "FONT")
    txt.body, txt.size, txt.align_x, txt.align_y, txt.resolution_u = str(j + 1), 0.22, "CENTER", "CENTER", 32
    add(root, txt, (0, 0.14), 0.003, mat(0, 0, 1))
    roots.append(root)
    anchors.append(anchor)

camd = bpy.data.cameras.new("cam")
camd.type = "ORTHO"
camob = bpy.data.objects.new("cam", camd)
sc.collection.objects.link(camob)
sc.camera = camob


def place(t):
    """t = 絵の番号 + 寄り具合。今いる絵 i を幅1で原点に、その先を縮小して入れ子に置く。"""
    i, u = int(t) % N, t - int(t)
    for ob in roots:
        ob.location = (0, 0, 50)  # カメラの後ろへ退避
    x = y = 0.0
    for d in range(DEPTH):
        j = (i + d) % N
        roots[j].location = (x, y, 0.1 * d)
        roots[j].scale = (S ** d,) * 3
        x += anchors[j][0] * S ** d
        y += anchors[j][1] * S ** d
    cx, cy, k = cam(anchors[i], u)
    camob.location = (cx, cy, 10)
    camd.ortho_scale = ASPECT * k  # 縦長なので ortho_scale は高さ側


sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 16
sc.cycles.use_denoising = False
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 720, 1280, 100
sc.render.use_persistent_data = True
sc.render.image_settings.file_format = "PNG"
sc.view_settings.view_transform = "Standard"

per_level = int(SEC_PER_LEVEL * FPS)
for f in range(0, N * per_level, STEP):
    place(f / per_level)
    sc.render.filepath = os.path.join(out_dir, f"{f:04d}.png")
    bpy.ops.render.render(write_still=True)
print("frames", N * per_level // STEP, "->", out_dir)
