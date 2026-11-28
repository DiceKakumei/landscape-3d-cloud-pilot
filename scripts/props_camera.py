"""
フィルムカメラ。巻き上げレバー→フィルムカウンターが1つ進む→絞りリングを回す→絞り羽根が閉じる→シャッターで羽根が一瞬閉じて開く→絞りを開放に戻す。
使い方: blender --background --python props_camera.py -- <start> <end> <outdir> [samples]
仕組みの出典: リサーチ/2026-11-28_懐中時計_絞り羽根_宝箱錠前の仕組み.md
1BU=1cm。カメラ正面は-Y。
"""
import bpy, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[sys.argv.index("--python") + 1])))
from props_lib import *

F0, F1, OUT, SAMPLES = args()
FEND = 144
reset()

CHROME = mat("chrome", (0.85, 0.86, 0.88), metal=1.0, rough=0.12)
SATIN = mat("satin", (0.7, 0.7, 0.72), metal=1.0, rough=0.35)
LEATHER = mat("leather", (0.03, 0.03, 0.03), rough=0.75)
BLACKM = mat("black_metal", (0.02, 0.02, 0.022), metal=0.6, rough=0.4)
BLADE = mat("blade", (0.05, 0.05, 0.055), metal=0.8, rough=0.3)
WHITE = mat("white_ink", (0.9, 0.9, 0.9), rough=0.4)
ORANGE = mat("orange_ink", (1.0, 0.45, 0.05), rough=0.4)
GLASS = mat("viewfinder", (0.1, 0.12, 0.15), metal=0.2, rough=0.03)
TABLE = mat("table", (0.5, 0.48, 0.45), rough=0.6)

box(60, 40, 1, (0, 0, -0.5), TABLE, bevel=0)
BW, BD, BH = 13.5, 3.2, 7.6
Z0 = BH / 2
box(BW, BD, BH * 0.62, (0, 0, BH * 0.31), LEATHER, bevel=0.35)  # 下半分(革)
box(BW, BD, BH * 0.4, (0, 0, BH * 0.8), CHROME, bevel=0.35)  # 上カバー
box(2.2, 0.1, 1.2, (-4.6, -BD / 2 - 0.02, BH * 0.82), GLASS, bevel=0.05)  # ファインダー窓
box(1.2, 0.1, 1.0, (4.4, -BD / 2 - 0.02, BH * 0.82), GLASS, bevel=0.05)  # 距離計窓


def text(s, size, loc, rot, m, parent, align="CENTER"):
    t = bpy.data.curves.new("t", "FONT"); t.body = s; t.size = size; t.align_x = align; t.align_y = "CENTER"
    o = bpy.data.objects.new("t", t); bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(m); o.parent = parent; o.location = loc; o.rotation_euler = rot
    return o

# ---------- レンズ(-Y方向に伸びる) ----------
LZ = BH * 0.42
lens = empty("lens", (0, -BD / 2, LZ))
cyl(2.4, 0.4, (0, -0.2, 0), CHROME, lens, axis="Y", v=96)  # マウント
apr = empty("aperture_ring", (0, -0.95, 0), lens)  # 絞りリング(回す)
cyl(2.2, 0.9, (0, 0, 0), SATIN, apr, axis="Y", v=96)
for k in range(48):  # ローレット
    a = 2 * PI * k / 48
    box(0.08, 0.5, 0.06, (2.21 * math.cos(a), -0.15, 2.21 * math.sin(a)), SATIN, apr, bevel=0, rot=(0, -a, 0))
FSTOPS = ["2.8", "4", "5.6", "8", "11", "16"]
STEP = math.radians(24)
for i, s in enumerate(FSTOPS):  # 数字は上側に並ぶ。リングをY軸回りに回すと目盛が動く
    a = PI / 2 + (i - 0) * STEP
    text(s, 0.32, (2.215 * math.cos(a), 0.25, 2.215 * math.sin(a)), (0, PI / 2 - a, 0), ORANGE if s == "16" else WHITE, apr)
box(0.06, 0.3, 0.25, (0, -0.4, 2.42), ORANGE, lens, bevel=0)  # 指標
focus = empty("focus", (0, -1.75, 0), lens)
cyl(2.05, 0.7, (0, 0, 0), BLACKM, focus, axis="Y", v=96)
for k in range(36):
    a = 2 * PI * k / 36
    box(0.12, 0.6, 0.1, (2.06 * math.cos(a), 0, 2.06 * math.sin(a)), BLACKM, focus, bevel=0, rot=(0, -a, 0))
torus(1.75, 0.08, (0, -2.6, 0), CHROME, lens, seg=96, axis="Y")
text("50mm 1:2.8", 0.16, (0, -2.61, 1.73), (PI / 2, 0, 0), WHITE, lens)
# 前面板(羽根の外側を隠すリング): 内径1.55
FR = empty("front_plate", (0, -2.45, 0), lens)
import bmesh
def annulus(name, r_in, r_out, thick, m, parent, loc):
    bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=False, radius=r_out, segments=96)
    outer = list(bm.verts); bmesh.ops.create_circle(bm, cap_ends=False, radius=r_in, segments=96)
    inner = [v for v in bm.verts if v not in outer]
    for i in range(96):
        bm.faces.new((outer[i], outer[(i + 1) % 96], inner[(i + 1) % 96], inner[i]))
    ext = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    bmesh.ops.translate(bm, vec=(0, 0, thick), verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    o.location = loc; o.rotation_euler = (PI / 2, 0, 0)
    return fin(o, m, parent, smooth=False)
annulus("front_plate", 1.5, 1.96, 0.05, BLACKM, lens, (0, -2.4, 0))
annulus("tip", 1.5, 1.95, 0.5, BLACKM, lens, (0, -2.1, 0))  # 先端

# ---------- 絞り羽根(7枚) ----------
# 各羽根: 半径1.6のピンを軸に回る弧状の板。全羽根が同じ角度だけ回ると開口が狭まる。
N = 7; RP = 1.6; R_IN = 1.05; R_OUT = 2.2; SPAN = math.radians(140)
def blade_pts(n=24):
    """羽根の形(ピンを原点、ピンが+X軸上にある向き)"""
    pts = []
    for i in range(n + 1):
        a = SPAN * i / n; pts.append((R_OUT * math.cos(a) - RP, R_OUT * math.sin(a)))
    for i in range(n, -1, -1):
        a = SPAN * i / n; pts.append((R_IN * math.cos(a) - RP, R_IN * math.sin(a)))
    return pts
BP = blade_pts()

def inner_radius(phi):
    """ピン回りにphi回した羽根1枚の、中心(=(-RP,0))からの最短距離 = 開口半径"""
    c, s = math.cos(phi), math.sin(phi); best = 9
    pts = [(x * c - y * s, x * s + y * c) for x, y in BP]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        dx, dy = x2 - x1, y2 - y1; px, py = -RP - x1, -y1
        t = max(0, min(1, (px * dx + py * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x1 + t * dx + RP, y1 + t * dy))
    return best

SGN = 1 if inner_radius(0.1) < inner_radius(-0.1) else -1  # 閉じる向き
def phi_for(r):
    lo, hi = 0.0, 0.66  # 二分探索(0.67付近で全閉、それ以上は形が崩れる)
    for _ in range(40):
        mid = (lo + hi) / 2
        if inner_radius(SGN * mid) > r: lo = mid
        else: hi = mid
    return SGN * (lo + hi) / 2
assert inner_radius(phi_for(0.4)) - 0.4 < 0.02  # 自己チェック: 狙った開口になる

IRIS = empty("iris", (0, -2.3, 0), lens, rot=(PI / 2, 0, 0))  # ローカルXY = レンズ正面の面
blades = []
for k in range(N):
    a = 2 * PI * k / N
    piv = empty(f"blade_{k}", (RP * math.cos(a), RP * math.sin(a), k * 0.004), IRIS)
    pr = empty("r", (0, 0, 0), piv, rot=(0, 0, a))  # ピンの向き
    pv = empty("phi", (0, 0, 0), pr)
    poly(f"blade_m{k}", BP, 0.003, BLADE, pv)
    cyl(0.05, 0.05, (0, 0, 0), SATIN, pv, v=12)
    blades.append(pv)
sphere(1.5, (0, -2.0, 0), mat("coated_glass", (0.01, 0.012, 0.02), rough=0.04), lens, scale=(1, 0.15, 1))  # 奥のレンズ(コーティングの反射)

# ---------- 上面: シャッターボタン・巻き上げレバー・カウンター・巻き戻しノブ ----------
TOP = BH
btn = empty("shutter", (3.6, 0.1, TOP))
cyl(0.45, 0.25, (3.6, 0.1, TOP + 0.1), CHROME, None)
cyl(0.28, 0.35, (0, 0, 0.3), CHROME, btn, v=32)
torus(0.28, 0.04, (3.6, 0.1, TOP + 0.25), CHROME, None)
lev = empty("lever", (5.1, 0.5, TOP + 0.15))
cyl(0.55, 0.15, (0, 0, 0), CHROME, lev, v=32)
poly("lever_arm", [(0, -0.15), (0, 0.15), (-2.6, 0.22), (-2.9, 0.0), (-2.6, -0.22)], 0.1, CHROME, lev)
cyl(0.22, 0.35, (-2.75, 0, 0.2), BLACKM, lev, v=16)  # 指当て
cnt = empty("counter", (2.2, 0.4, TOP + 0.05))
cyl(0.5, 0.03, (0, 0, 0), BLACKM, cnt, v=48)
for i in range(0, 40, 2):
    a = PI / 2 - i * 2 * PI / 40
    text(str(i) if i % 4 == 0 else ".", 0.13, (0.36 * math.cos(a), 0.36 * math.sin(a), 0.02), (0, 0, a - PI / 2), WHITE, cnt)
cyl(0.62, 0.05, (2.2, 0.4, TOP + 0.08), mat("cnt_glass", (1, 1, 1), rough=0.0, transmission=1.0), None)
rw = empty("rewind", (-4.8, 0.2, TOP))
cyl(0.7, 0.5, (0, 0, 0.25), CHROME, rw, v=48)
for k in range(24):
    a = 2 * PI * k / 24
    box(0.06, 0.06, 0.45, (0.71 * math.cos(a), 0.71 * math.sin(a), 0.25), CHROME, rw, bevel=0)
box(1.6, 1.4, 0.15, (-1.2, 0, TOP + 0.08), CHROME, bevel=0.05)  # アクセサリーシュー
text("RANGEFINDER", 0.3, (-1.6, -BD / 2 - 0.02, BH * 0.95), (PI / 2, 0, 0), BLACKM, None)

# ---------- 動き ----------
def lever_angle(f):  # 巻き上げ: 振り出して戻る(バネ)
    return -math.radians(130) * (seg(f, 8, 22) - seg(f, 24, 32))  # 親指で手前(+Y)へ引く
def counter_angle(f):  # レバーと連動して1コマ(1/40回転)
    return -(2 * PI / 40) * (12 + seg(f, 10, 22))
def ring_steps(f):  # 絞りの段数(0=2.8, 5=16)
    return 5 * seg(f, 44, 66) - 5 * seg(f, 110, 130)
def aperture(steps):  # f値に応じた開口半径: 開放1.0 → f16 0.18
    fnum = 2.8 * (2 ** 0.5) ** (steps)
    return 1.02 * 2.8 / fnum
def shutter(f):  # 押した瞬間に羽根が閉じて開く
    if 80 <= f <= 82: return 0.0
    return 1.0

for f in range(1, FEND + 1):
    lev.rotation_euler.z = lever_angle(f); key_rot(lev, f, 2)
    cnt.rotation_euler.z = counter_angle(f); key_rot(cnt, f, 2)
    st = ring_steps(f)
    apr.rotation_euler.y = st * STEP; key_rot(apr, f, 1)
    ph = phi_for(aperture(st) if shutter(f) else 0.03)
    for pv in blades:
        pv.rotation_euler.z = ph; key_rot(pv, f, 2)
    btn.location.z = TOP - 0.12 * (seg(f, 76, 79) - seg(f, 83, 88)); btn.keyframe_insert("location", index=2, frame=f)

# ---------- カメラ・光 ----------
camera([
    (1, (9, -16, 12), (1.0, 0, 5.0)),
    (30, (8, -14, 13), (2.5, 0, 6.0)),
    (48, (2.5, -11, 5.5), (0, -3, 3.2)),
    (74, (0.6, -9.0, 3.6), (0, -3, 3.2)),
    (100, (0.4, -8.6, 3.4), (0, -3, 3.2)),
    (144, (7, -15, 9), (0.5, 0, 4.0)),
], lens=50)
C = (0, 0, 3.5)
area((-10, -12, 16), 3500, 10, (1.0, 0.95, 0.88), C)
area((12, -4, 8), 1500, 6, (0.8, 0.88, 1.0), C)
area((0, -10, 3), 500, 4, (1, 1, 1), (0, -3, 3.2))
world((0.18, 0.18, 0.19))
render(F0, F1, OUT, SAMPLES, FEND)
