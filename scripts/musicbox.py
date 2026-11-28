"""
部品が分かれて動くオルゴール(試作)。全部bpyで組む。1BU=1cm。
使い方: blender --background --python musicbox.py -- <start> <end> <outdir> [samples]
動き: ボタンを押す→蓋が開く→ゼンマイ車→シリンダー→ガバナー車→羽根車が回り、シリンダーのピンが櫛歯を弾く。
寸法の出典: リサーチ/2026-11-28_オルゴールの機構と寸法.md
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
F0, F1, OUT = int(argv[0]), int(argv[1]), argv[2]
SAMPLES = int(argv[3]) if len(argv) > 3 else 24
FEND = 144
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
PI = math.pi


# ---------- 素材 ----------
def mat(name, color, metal=0.0, rough=0.5, wood=False):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if wood:  # 木目: 波テクスチャを歪ませて濃淡に
        w = nt.nodes.new("ShaderNodeTexWave"); w.inputs["Scale"].default_value = 1.2
        w.inputs["Distortion"].default_value = 6.0; w.inputs["Detail"].default_value = 3
        r = nt.nodes.new("ShaderNodeValToRGB")
        r.color_ramp.elements[0].color = (color[0] * 0.55, color[1] * 0.5, color[2] * 0.45, 1)
        r.color_ramp.elements[1].color = (*color, 1)
        nt.links.new(w.outputs["Fac"], r.inputs["Fac"]); nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    return m


WOOD = mat("wood", (0.42, 0.2, 0.08), rough=0.35, wood=True)
TABLE = mat("table", (0.16, 0.09, 0.05), rough=0.5, wood=True)
VELVET = mat("velvet", (0.35, 0.02, 0.04), rough=0.9)
BRASS = mat("brass", (0.85, 0.62, 0.3), metal=1.0, rough=0.25)
STEEL = mat("steel", (0.75, 0.76, 0.78), metal=1.0, rough=0.18)
DARK = mat("dark_steel", (0.2, 0.2, 0.22), metal=1.0, rough=0.35)


# ---------- 形 ----------
def fin(o, m, parent=None):
    o.data.materials.append(m)
    if parent: o.parent = parent
    for p in o.data.polygons: p.use_smooth = True
    return o


def box(sx, sy, sz, loc, m, parent=None, bevel=0.05):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object
    o.scale = (sx, sy, sz); bpy.ops.object.transform_apply(scale=True)
    if bevel:
        bv = o.modifiers.new("bv", "BEVEL"); bv.width = bevel; bv.segments = 2
    fin(o, m, parent)
    for p in o.data.polygons: p.use_smooth = False
    return o


def cyl_x(r, length, loc, m, parent=None, v=48):
    """X軸向きの円柱"""
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=length, vertices=v, location=loc, rotation=(0, PI / 2, 0))
    return fin(bpy.context.object, m, parent)


def empty(name, loc, parent=None):
    o = bpy.data.objects.new(name, None); sc.collection.objects.link(o)
    o.location = loc
    if parent: o.parent = parent
    return o


def gear(name, r, teeth, thick, m, loc, parent=None, hub=0.25):
    """X軸を回転軸とする平歯車。歯0番が+Y方向(回転角0)を向く。"""
    bm = bmesh.new(); h = 2 * r / teeth  # 歯の高さ≒モジュール
    pts = []
    for k in range(teeth):
        a = 2 * PI * k / teeth; s = PI / teeth
        for da, rr in ((-s * 0.55, r - h * 0.6), (-s * 0.28, r + h * 0.5), (s * 0.28, r + h * 0.5), (s * 0.55, r - h * 0.6)):
            pts.append(bm.verts.new((-thick / 2, rr * math.cos(a + da), rr * math.sin(a + da))))
    f = bm.faces.new(pts)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=(thick, 0, 0), verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o.location = loc
    o.data.materials.append(m)
    if parent: o.parent = parent
    cyl_x(hub, thick * 1.6, (0, 0, 0), m, o)  # ハブ
    # 軽量化の穴の代わりに4本スポークの溝(暗い円盤)で歯車らしく
    if r > 0.6:
        cyl_x(r * 0.72, thick * 1.02, (0, 0, 0), DARK, o)
        for k in range(4):
            b = box(thick * 1.1, r * 1.4, r * 0.14, (0, 0, 0), m, o, bevel=0)
            b.rotation_euler.x = k * PI / 4
    return o


# ---------- 箱 ----------
BW, BD, BH, LH, T = 12.0, 9.0, 4.0, 2.0, 0.6
box(40, 30, 1, (0, 0, -0.5), TABLE, bevel=0)  # テーブル
box(BW, BD, T, (0, 0, T / 2), WOOD)  # 底
box(BW, T, BH, (0, -BD / 2 + T / 2, BH / 2), WOOD)  # 前
box(BW, T, BH, (0, BD / 2 - T / 2, BH / 2), WOOD)  # 後
box(T, BD, BH, (-BW / 2 + T / 2, 0, BH / 2), WOOD)  # 左
box(T, BD, BH, (BW / 2 - T / 2, 0, BH / 2), WOOD)  # 右
box(BW - 2 * T, BD - 2 * T, 0.05, (0, 0, T + 0.03), VELVET, bevel=0)  # 内張り

# 蓋: 後ろ上辺の蝶番まわりに回る
hinge = empty("lid_hinge", (0, BD / 2, BH))
box(BW, BD, 0.5, (0, -BD / 2, LH - 0.25), WOOD, hinge)  # 天板
box(BW, T, LH - 0.5, (0, -BD + T / 2, (LH - 0.5) / 2), WOOD, hinge)
box(BW, T, LH - 0.5, (0, -T / 2, (LH - 0.5) / 2), WOOD, hinge)
box(T, BD, LH - 0.5, (-BW / 2 + T / 2, -BD / 2, (LH - 0.5) / 2), WOOD, hinge)
box(T, BD, LH - 0.5, (BW / 2 - T / 2, -BD / 2, (LH - 0.5) / 2), WOOD, hinge)
box(BW - 2 * T, BD - 2 * T, 0.05, (0, -BD / 2, LH - 0.55), VELVET, hinge, bevel=0)
for x in (-3.5, 3.5):  # 蝶番の金具
    cyl_x(0.18, 1.6, (x, BD / 2 + 0.05, BH), BRASS)

# 前面の押しボタン(真鍮)と台座
bpy.ops.mesh.primitive_cylinder_add(radius=0.55, depth=0.15, location=(0, -BD / 2 - 0.05, BH * 0.55), rotation=(PI / 2, 0, 0))
fin(bpy.context.object, BRASS)
bpy.ops.mesh.primitive_cylinder_add(radius=0.38, depth=0.4, location=(0, -BD / 2 - 0.3, BH * 0.55), rotation=(PI / 2, 0, 0))
button = fin(bpy.context.object, BRASS)

# ---------- ムーブメント ----------
MV = empty("movement", (0, 0.3, T + 0.05))
box(5.6, 4.6, 0.2, (0, 0, 0.1), BRASS, MV)  # 台板
CY, CZ, CR, CL = 0.6, 2.0, 0.95, 3.2  # シリンダー中心(y,z)・半径・長さ
for x in (-CL / 2 - 0.2, CL / 2 + 0.2):  # 軸受けの柱
    box(0.2, 0.6, CZ, (x, CY, CZ / 2 + 0.1), BRASS, MV)
cyl_x(0.08, CL + 1.2, (0, CY, CZ), STEEL, MV)  # 軸

cyl_rot = empty("cylinder_rot", (0, CY, CZ), MV)
cyl_x(CR, CL, (0, 0, 0), BRASS, cyl_rot, v=96)

# 櫛歯: 18本、根元のブロックから+Y方向へ伸び、先端がシリンダー前面に触れる
NT = 18
tooth_x = [-1.45 + 2.9 * i / (NT - 1) for i in range(NT)]
TIP_Y = CY - CR - 0.06
BASE_Y = -1.6
box(3.4, 0.7, 0.35, (0, BASE_Y - 0.35, CZ - 0.05), STEEL, MV)  # 櫛の根元
box(3.4, 0.9, CZ - 0.2, (0, BASE_Y - 0.35, (CZ - 0.2) / 2 + 0.2), BRASS, MV)  # 台
teeth = []
for i, x in enumerate(tooth_x):
    piv = empty(f"tooth_{i}", (x, BASE_Y, CZ), MV)
    L = TIP_Y - BASE_Y
    box(0.12, L, 0.05, (0, L / 2, 0), STEEL, piv, bevel=0.01)
    teeth.append(piv)

# 歯車列: ゼンマイ車B(42) → シリンダー大歯車C(30) → ピニオンP(8) / 同軸の車W(24) → 羽根のピニオンQ(6)
M_ = 2 * 1.0 / 30  # モジュール(全歯車共通)
GX = CL / 2 + 0.55  # 歯車を並べる面(x)
def r_of(t): return M_ * t / 2

gears = {}  # name -> (obj, teeth, center(y,z))
def place(name, t, yz, x, m=BRASS, thick=0.18):
    o = gear(name, r_of(t), t, thick, m, (x, yz[0], yz[1]), MV)
    gears[name] = (o, t, yz)
    return o

C = place("C", 30, (CY, CZ), GX)
cyl_x(0.12, 0.6, (GX, CY, CZ), STEEL, MV)
aB = math.radians(45)  # Bの位置: Cから後ろ上(閉じた蓋の内側に収まる高さ)
dB = r_of(30) + r_of(36)
place("B", 36, (CY + dB * math.cos(aB), CZ + dB * math.sin(aB)), GX)
barrel_yz = gears["B"][2]
barrel = cyl_x(r_of(36) * 0.75, 0.6, (GX - 0.45, *barrel_yz), BRASS, MV)  # ゼンマイの香箱
aP = math.radians(150)  # Pの位置: Cから前上
dP = r_of(30) + r_of(8)
P_yz = (CY + dP * math.cos(aP), CZ + dP * math.sin(aP))
place("P", 8, P_yz, GX, STEEL)
place("W", 24, P_yz, GX + 0.3)
cyl_x(0.05, 0.9, (GX + 0.2, *P_yz), STEEL, MV)
aQ = math.radians(100)
dQ = r_of(24) + r_of(6)
Q_yz = (P_yz[0] + dQ * math.cos(aQ), P_yz[1] + dQ * math.sin(aQ))
place("Q", 6, Q_yz, GX + 0.3, STEEL)
cyl_x(0.04, 1.0, (GX + 0.55, *Q_yz), STEEL, MV)
fan = empty("fan", (GX + 0.9, *Q_yz), MV)  # ガバナーの羽根(2枚)
for s in (1, -1):
    b = box(0.03, 0.12, 0.55, (0, 0, s * 0.33), STEEL, fan, bevel=0.01)
cyl_x(0.07, 0.1, (0, 0, 0), STEEL, fan)


# ---------- 動き ----------
def ease(t): t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)


def cyl_angle(f):
    """シリンダーの回転角(負方向=前面が上に動く)。f40から加速、f56以降一定速度。"""
    W_ = -0.026  # rad/frame
    if f <= 40: return 0.0
    if f <= 56: return W_ * (f - 40) ** 2 / (2 * 16)
    return W_ * 8 + W_ * (f - 56)


# 噛み合わせ: 回転角0で歯0番が+Y。駆動側の歯が相手方向aを向くとき、相手は a+π に歯溝を向ける
phase = {"C": 0.0}
ratio = {"C": 1.0}
def link(drv, drn):
    _, td, yd = gears[drv]; _, tn, yn = gears[drn]
    a = math.atan2(yn[1] - yd[1], yn[0] - yd[0])
    # drvの歯がaを向くのはdrv角= a - phase_drv(歯の周期で)。そのときdrnは a+π に歯溝を向ける
    k = round((a - phase[drv]) / (2 * PI / td))
    th_d = phase[drv] + k * 2 * PI / td
    ratio[drn] = -ratio[drv] * td / tn
    # drv角θ_d=th_dのとき drn角 = a+π+π/tn。線形関係 θ_n = phase_n + ratio_n*θ_C
    th_C = (th_d - phase[drv]) / ratio[drv] if ratio[drv] else 0
    phase[drn] = (a + PI + PI / tn) - ratio[drn] * th_C - 0  # θ_n(θ_C)
link("C", "B"); link("C", "P")
ratio["W"] = ratio["P"]; phase["W"] = 0.0
link("W", "Q")

# 曲: f58から4フレームおきに1音。櫛歯の番号(0=低音)
melody = [0, 4, 7, 11, 14, 11, 7, 4, 2, 6, 9, 13, 16, 13, 9, 6, 4, 7, 11, 14, 17, 14]
plucks = {i: [] for i in range(NT)}
for n, ti in enumerate(melody):
    fp = 58 + 4 * n
    if fp > FEND - 2: break
    plucks[ti].append(fp)
    a0 = PI - cyl_angle(fp)  # このフレームでピンが真前(角π)に来る
    pin = empty(f"pin_{n}", (tooth_x[ti], 0, 0), cyl_rot)
    pin.rotation_euler.x = a0
    bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.16, vertices=8, location=(0, 0, 0))
    p = fin(bpy.context.object, STEEL, pin); p.location = (0, CR + 0.02, 0); p.rotation_euler.x = PI / 2
# 飾りのピン: 動画中に前を通らない側に並べる
import random
rng = random.Random(3)
sweep = -cyl_angle(FEND)
for n in range(60):
    a0 = PI + sweep + 0.2 + rng.random() * (2 * PI - sweep - 0.4)
    pin = empty(f"deco_pin_{n}", (rng.choice(tooth_x), 0, 0), cyl_rot); pin.rotation_euler.x = a0
    bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.16, vertices=8, location=(0, 0, 0))
    p = fin(bpy.context.object, STEEL, pin); p.location = (0, CR + 0.02, 0); p.rotation_euler.x = PI / 2


def tooth_angle(i, f):
    a = 0.0; LIFT = math.radians(5)
    for fp in plucks[i]:
        if fp - 3 <= f <= fp: a += LIFT * (1 - (fp - f) / 3)  # ピンに押し上げられる
        elif f > fp: a += LIFT * math.exp(-(f - fp) / 5) * math.cos(PI * (f - fp) * 0.9)  # 離れて震える
    return a


def lid_angle(f):
    t = (f - 20) / 30
    if t <= 0: return 0.0
    if t >= 1: return math.radians(-105)
    return math.radians(-105) * (ease(t) + 0.06 * math.sin(t * PI) * t)  # 少し行き過ぎて戻る


def button_y(f):
    if 10 <= f <= 15: return -0.25 * ease((f - 10) / 5)
    if 15 < f <= 22: return -0.25 * (1 - ease((f - 15) / 7))
    return 0.0


by0 = button.location.y
for f in range(1, FEND + 1):
    th = cyl_angle(f)
    cyl_rot.rotation_euler.x = th; cyl_rot.keyframe_insert("rotation_euler", index=0, frame=f)
    for g, (o, _, _) in gears.items():
        o.rotation_euler.x = phase[g] + ratio[g] * th; o.keyframe_insert("rotation_euler", index=0, frame=f)
    fan.rotation_euler.x = ratio["Q"] * th; fan.keyframe_insert("rotation_euler", index=0, frame=f)
    for i, tp in enumerate(teeth):
        tp.rotation_euler.x = tooth_angle(i, f); tp.keyframe_insert("rotation_euler", index=0, frame=f)
    hinge.rotation_euler.x = lid_angle(f); hinge.keyframe_insert("rotation_euler", index=0, frame=f)
    button.location.y = by0 - button_y(f); button.keyframe_insert("location", index=1, frame=f)

# ---------- カメラ・光 ----------
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 50; cam_d.clip_start = 0.1
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
tgt = empty("cam_target", (0, 0, 2.5))
tr = cam.constraints.new("TRACK_TO"); tr.target = tgt; tr.track_axis = "TRACK_NEGATIVE_Z"; tr.up_axis = "UP_Y"
shots = [  # (frame, cam loc, target loc)
    (1, (6, -24, 12), (0, 0, 3.0)),
    (36, (5, -22, 13), (0, 0, 3.5)),
    (80, (6.5, -9.5, 7.5), (0.6, 0.6, 2.4)),
    (120, (7.5, -7.0, 5.6), (0.9, 0.7, 2.6)),
    (144, (7.8, -6.6, 5.3), (1.0, 0.7, 2.6)),
]
for f, cl, tl in shots:
    cam.location = cl; cam.keyframe_insert("location", frame=f)
    tgt.location = tl; tgt.keyframe_insert("location", frame=f)

def area(loc, energy, size, color=(1, 1, 1)):
    d = bpy.data.lights.new("a", "AREA"); d.energy = energy; d.size = size; d.color = color
    o = bpy.data.objects.new("a", d); sc.collection.objects.link(o); o.location = loc
    t = o.constraints.new("TRACK_TO"); t.target = empty("lt", (0, 0, 2)); t.track_axis = "TRACK_NEGATIVE_Z"
area((-10, -12, 18), 4000, 10, (1.0, 0.9, 0.78))
area((14, 4, 10), 1500, 6, (0.7, 0.8, 1.0))
area((2, -6, 12), 600, 3, (1.0, 0.95, 0.9))

w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.018, 0.016, 1)

# ---------- 描画 ----------
try: sc.render.engine = "CYCLES"
except TypeError as e: print(e)
sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 960, 540
sc.render.fps = 24
sc.view_settings.view_transform = "AgX"
sc.render.image_settings.file_format = "PNG"
os.makedirs(OUT, exist_ok=True)
for f in range(F0, F1 + 1):
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, f"f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
print("done", F0, F1)
