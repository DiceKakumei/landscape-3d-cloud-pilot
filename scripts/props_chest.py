"""
宝箱の錠前。鍵が鍵穴に入る→1回転→鍵の先(ビット)がかんぬきを押して滑らせる→掛け金(ハスプ)の輪が外れる→蓋が開く。
錠前の前板はガラス(切断面の代わり)にして、中のかんぬきと鍵の動きが見えるようにする。
使い方: blender --background --python props_chest.py -- <start> <end> <outdir> [samples]
仕組みの出典: リサーチ/2026-11-28_懐中時計_絞り羽根_宝箱錠前の仕組み.md
1BU=1cm。正面は-Y。
"""
import bpy, bmesh, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[sys.argv.index("--python") + 1])))
from props_lib import *

F0, F1, OUT, SAMPLES = args()
FEND = 144
reset()

WOOD = mat("wood", (0.36, 0.17, 0.07), rough=0.55, wood=True)
IRON = mat("iron", (0.13, 0.12, 0.11), metal=1.0, rough=0.55)
BRASS = mat("brass", (0.85, 0.6, 0.28), metal=1.0, rough=0.28)
STEEL = mat("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.3)
GLASS = mat("glass", (0.9, 0.95, 1.0), rough=0.02, transmission=1.0)
GOLD = mat("gold", (1.0, 0.7, 0.25), metal=1.0, rough=0.18)
GEM = mat("gem", (0.05, 0.6, 0.2), rough=0.02, transmission=0.8)
FLOOR = mat("floor", (0.22, 0.2, 0.18), rough=0.8)
DARK = mat("dark", (0.01, 0.01, 0.01), rough=1.0)

box(60, 40, 1, (0, 0, -0.5), FLOOR, bevel=0)
CW, CD, CH, T = 10.0, 6.5, 5.0, 0.4  # 箱の幅・奥行・高さ・板厚
box(CW, CD, T, (0, 0, T / 2), WOOD)
box(CW, T, CH, (0, -CD / 2 + T / 2, CH / 2), WOOD)
box(CW, T, CH, (0, CD / 2 - T / 2, CH / 2), WOOD)
box(T, CD - 2 * T, CH, (-CW / 2 + T / 2, 0, CH / 2), WOOD)
box(T, CD - 2 * T, CH, (CW / 2 - T / 2, 0, CH / 2), WOOD)
for x in (-CW / 2 + 0.9, CW / 2 - 0.9):  # 鉄の帯(箱)
    box(0.5, CD + 0.08, 0.06, (x, 0, CH - 0.03), IRON, bevel=0)
    box(0.5, 0.06, CH, (x, -CD / 2 - 0.03, CH / 2), IRON, bevel=0)
    box(0.5, 0.06, CH, (x, CD / 2 + 0.03, CH / 2), IRON, bevel=0)
for xs in (-1, 1):  # 角金具
    for ys in (-1, 1):
        box(0.7, 0.7, 0.7, (xs * (CW / 2 - 0.3), ys * (CD / 2 - 0.3), 0.35), IRON, bevel=0.06)


def half_shell(name, r, length, zscale, m, parent, loc, thick=None, segs=48):
    """X軸向きの半円筒(上半分)。thickを渡すと殻、無ければ中身あり。"""
    bm = bmesh.new()
    def ring(rr, x):
        return [bm.verts.new((x, rr * math.cos(PI * i / segs), rr * math.sin(PI * i / segs) * zscale)) for i in range(segs + 1)]
    if thick is None:
        a, b = ring(r, -length / 2), ring(r, length / 2)
        for i in range(segs): bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
        bm.faces.new(a); bm.faces.new(list(reversed(b))); bm.faces.new((a[0], b[0], b[-1], a[-1]))
    else:
        ao, bo, ai, bi = ring(r, -length / 2), ring(r, length / 2), ring(r - thick, -length / 2), ring(r - thick, length / 2)
        for i in range(segs):
            bm.faces.new((ao[i], ao[i + 1], bo[i + 1], bo[i])); bm.faces.new((ai[i + 1], ai[i], bi[i], bi[i + 1]))
            bm.faces.new((ao[i + 1], ao[i], ai[i], ai[i + 1])); bm.faces.new((bo[i], bo[i + 1], bi[i + 1], bi[i]))
        bm.faces.new((ao[0], ai[0], bi[0], bo[0])); bm.faces.new((ao[-1], bo[-1], bi[-1], ai[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o); o.location = loc
    return fin(o, m, parent)

# ---------- 蓋(後ろ上辺の蝶番まわり) ----------
LR, LZS = CD / 2, 0.55
lid = empty("lid", (0, CD / 2, CH))
half_shell("lid_shell", LR, CW, LZS, WOOD, lid, (0, -CD / 2, 0), thick=0.35)
for sx in (-1, 1):  # 蓋の妻板(半円)
    half_shell("lid_end", LR - 0.02, T, LZS, WOOD, lid, (sx * (CW / 2 - T / 2), -CD / 2, 0))
for x in (-CW / 2 + 0.9, CW / 2 - 0.9):
    half_shell("lid_band", LR + 0.05, 0.5, LZS * (LR + 0.05) / LR * 1.0, IRON, lid, (x, -CD / 2, 0), thick=0.06)
box(CW, 0.5, 0.15, (0, -CD + 0.25, 0.075), WOOD, lid, bevel=0.03)  # 前の縁
for x in (-3, 3):
    cyl(0.18, 1.4, (x, CD / 2 + 0.05, CH), IRON, axis="X")  # 蝶番

# ハスプ(掛け金): 蓋の前縁に蝶番で付く短い舌。先の輪(ステープル)が錠前の上の口から中へ入る
LOCK_Z = CH - 1.6  # 錠前の中心高さ
hasp = empty("hasp", (0, -CD - 0.05, 0.0), lid)
cyl(0.1, 1.0, (0, 0, 0), IRON, hasp, axis="X")
box(0.8, 0.5, 0.08, (0, -0.25, 0), IRON, hasp, bevel=0.02)
box(0.12, 0.12, 0.3, (0, -0.35, -0.15), IRON, hasp, bevel=0)
torus(0.3, 0.05, (0, -0.35, -0.6), IRON, hasp, axis="X")  # 輪: かんぬきがこの中を通ると開かない

# ---------- 錠前(表付け錠): 鉄の枠 + ガラスの前板 ----------
LK = empty("lock", (0, -CD / 2 - 0.05, LOCK_Z))
LW, LH, LDp = 2.8, 2.6, 0.7
box(LW, LDp, 0.15, (0, -LDp / 2, LH / 2 - 0.075), IRON, LK, bevel=0.03)
box(LW, LDp, 0.15, (0, -LDp / 2, -LH / 2 + 0.075), IRON, LK, bevel=0.03)
box(0.15, LDp, LH, (-LW / 2 + 0.075, -LDp / 2, 0), IRON, LK, bevel=0.03)
box(0.15, LDp, LH, (LW / 2 - 0.075, -LDp / 2, 0), IRON, LK, bevel=0.03)
box(LW, 0.05, LH, (0, -0.02, 0), IRON, LK, bevel=0)  # 背板
box(LW - 0.1, 0.04, LH - 0.1, (0, -LDp + 0.02, 0), GLASS, LK, bevel=0)  # 前板(ガラス)
box(0.2, 0.65, 0.16, (0, -0.35, LH / 2 + 0.01), DARK, LK, bevel=0)  # 上面の差し込み口
# 鍵穴の座金(ガラスに付く真鍮板): 円+下向きの溝
KZ = -0.2
esc = empty("escutcheon", (0, -LDp - 0.01, KZ), LK)
poly("esc_plate", [(0.42 * math.cos(a), 0.42 * math.sin(a)) for a in [2 * PI * i / 32 for i in range(32)]], 0.04, BRASS, esc).rotation_euler = (PI / 2, 0, 0)
cyl(0.1, 0.06, (0, -0.01, 0.05), DARK, esc, axis="Y", v=16)
box(0.07, 0.06, 0.22, (0, -0.01, -0.08), DARK, esc, bevel=0)
# かんぬき: 輪を貫く鉄の棒(左へ0.45滑ると輪から抜ける)。下に鍵の先が押す爪(タロン)
BZ = 1.0
bolt = empty("bolt", (0, -0.35, BZ), LK)
box(1.5, 0.25, 0.25, (-0.5, 0, 0), STEEL, bolt, bevel=0.03)
box(0.14, 0.25, 0.7, (0.12, 0, -0.48), STEEL, bolt, bevel=0.02)
box(0.6, 0.3, 0.06, (-0.9, -0.05, BZ - 0.16), IRON, LK, bevel=0)  # 受け
# 鍵(ローカル+Yが錠前の奥)
key = empty("key", (0, -LDp - 3.0, KZ), LK)
kr = empty("key_rot", (0, 0, 0), key)
cyl(0.07, 0.95, (0, -0.025, 0), BRASS, kr, axis="Y", v=16)  # 軸
torus(0.12, 0.05, (0, 0.0, 0), BRASS, kr, axis="Y")  # つば
torus(0.42, 0.08, (0, -0.95, 0), BRASS, kr, axis="X")  # 握り(輪)
box(0.08, 0.2, 0.55, (0, 0.3, -0.3), BRASS, kr, bevel=0.01)  # ビット: 下向き。回すと上で爪を押す

# ---------- 中身 ----------
import random
rng = random.Random(4)
for i in range(140):
    x = rng.uniform(-4.2, 4.2); y = rng.uniform(-2.5, 2.5)
    z = 0.4 + 2.6 * math.exp(-(x * x / 14 + y * y / 6)) + rng.uniform(0, 0.3)
    c = cyl(0.42, 0.07, (x, y, z), GOLD, None, v=24)
    c.rotation_euler = (rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0)
for p, m in (((1.2, 0.5, 3.3), GEM), ((-1.5, -0.4, 3.0), mat("ruby", (0.7, 0.02, 0.05), rough=0.02, transmission=0.8))):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=0.45, subdivisions=1, location=p); fin(bpy.context.object, m, None, smooth=False)
glow = bpy.data.lights.new("glow", "POINT"); glow.color = (1.0, 0.75, 0.35); glow.shadow_soft_size = 2.0
gl = bpy.data.objects.new("glow", glow); bpy.context.scene.collection.objects.link(gl); gl.location = (0, 0, 4.5)

# ---------- 動き ----------
def key_in(f): return (3.0 - 0.02) * seg(f, 10, 30)  # 鍵が鍵穴へ
def key_turn(f): return -2 * PI * seg(f, 36, 72)  # 反時計回りに1回転(正面から)
def bolt_x(f):
    """ビットが真上を通る(回転角150°〜210°)あいだだけ、かんぬきを左へ0.45押す"""
    a = -key_turn(f)
    return -0.45 * max(0.0, min(1.0, (a - math.radians(150)) / math.radians(60)))
def lid_angle(f): return -math.radians(105) * seg(f, 80, 112)

for f in range(1, FEND + 1):
    key.location.y = -LDp - 3.0 + key_in(f); key.keyframe_insert("location", index=1, frame=f)
    kr.rotation_euler.y = -key_turn(f); key_rot(kr, f, 1)  # +Y軸回りの正 = 正面(-Y)から見て反時計回り
    bolt.location.x = bolt_x(f); bolt.keyframe_insert("location", index=0, frame=f)
    la = lid_angle(f)
    lid.rotation_euler.x = la; key_rot(lid, f, 0)
    hasp.rotation_euler.x = -la * 0.85; key_rot(hasp, f, 0)  # 掛け金は垂れ下がったまま
    glow.energy = 400 * seg(f, 85, 115); glow.keyframe_insert("energy", frame=f)

# ---------- カメラ・光 ----------
camera([
    (1, (7, -20, 11), (0, 0, 3.2)),
    (14, (4, -14, 6.5), (0, -3, 3.4)),
    (34, (2.2, -10.0, 4.6), (0, -3.6, 3.3)),
    (74, (1.6, -9.3, 4.3), (0, -3.6, 3.3)),
    (100, (5, -17, 12), (0, 0, 3.6)),
    (144, (2.5, -12, 13), (0, 0.3, 2.6)),
], lens=50)
C = (0, 0, 3)
area((-10, -12, 15), 3000, 10, (1.0, 0.85, 0.65), C)
area((12, -6, 8), 1200, 6, (0.6, 0.7, 1.0), C)
area((0, -10, 4), 300, 4, (1, 1, 1), (0, -3.6, 3.3))
world((0.015, 0.015, 0.02))
render(F0, F1, OUT, SAMPLES, FEND)
