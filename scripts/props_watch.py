"""
懐中時計(ハンターケース)。竜頭を押す→前蓋が開く→秒針が刻む→裏蓋が開く→テンプ・アンクル・輪列が動く。
使い方: blender --background --python props_watch.py -- <start> <end> <outdir> [samples]
仕組みの出典: リサーチ/2026-11-28_懐中時計_絞り羽根_宝箱錠前の仕組み.md
1BU=1cm。時計の座標(ローカル): +Zが文字盤側、+Yが12時、+Xが3時(竜頭・蝶番は9時)。
"""
import bpy, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[sys.argv.index("--python") + 1])))
from props_lib import *

F0, F1, OUT, SAMPLES = args()
FEND = 144
reset()

GOLD = mat("gold", (1.0, 0.72, 0.35), metal=1.0, rough=0.2)
GOLD_M = mat("gold_matte", (0.95, 0.68, 0.33), metal=1.0, rough=0.45)
NICKEL = mat("nickel", (0.8, 0.8, 0.78), metal=1.0, rough=0.32)
ENAMEL = mat("enamel", (0.93, 0.91, 0.86), rough=0.15)
BLUE = mat("blued_steel", (0.05, 0.08, 0.3), metal=1.0, rough=0.2)
BLACK = mat("ink", (0.02, 0.02, 0.02), rough=0.4)
RUBY = mat("ruby", (0.7, 0.02, 0.05), rough=0.05, transmission=0.6)
DARK = mat("dark", (0.15, 0.13, 0.1), metal=1.0, rough=0.4)
GLASS = mat("glass", (1, 1, 1), rough=0.0, transmission=1.0)
WOOD = mat("wood", (0.3, 0.14, 0.06), rough=0.4, wood=True)
CLOTH = mat("cloth", (0.06, 0.12, 0.09), rough=0.95)

R = 2.5  # ケース半径(直径50mm)
box(40, 30, 1, (0, 0, -0.5), CLOTH, bevel=0)
box(3.2, 2.0, 0.6, (0, 0, 0.3), WOOD, bevel=0.1)  # 台
W = empty("watch", (0, 0, 0.6 + R + 0.05), rot=(PI / 2, 0, 0))  # ローカル+Z=ワールド-Y(カメラ側)

# ---------- ケース ----------
cyl(R, 1.0, (0, 0, 0), GOLD, W, v=96)  # 胴
torus(R - 0.05, 0.12, (0, 0, 0.5), GOLD, W, seg=96)  # ベゼル
cyl(2.25, 0.02, (0, 0, 0.51), ENAMEL, W, v=96)  # 文字盤
s = sphere(2.3, (0, 0, 0.45), GLASS, W, scale=(1, 1, 0.12))  # 風防
# 竜頭・リューズ環(3時)
stem = cyl(0.12, 0.5, (R + 0.2, 0, 0), GOLD, W, axis="X")
crown = empty("crown", (R + 0.6, 0, 0), W)
cyl(0.3, 0.35, (0, 0, 0), GOLD, crown, axis="X", v=24)
for k in range(16):  # ギザ
    a = 2 * PI * k / 16
    box(0.33, 0.05, 0.05, (0, 0.31 * math.cos(a), 0.31 * math.sin(a)), GOLD, crown, bevel=0, rot=(a, 0, 0))
torus(0.6, 0.09, (R + 0.65, 0, 0), GOLD, W)  # 環(ボウ)

# 文字盤: 時刻の目盛と数字
for h in range(1, 13):
    a = PI / 2 - h * PI / 6
    t = bpy.data.curves.new(f"n{h}", "FONT"); t.body = str(h); t.align_x = "CENTER"; t.align_y = "CENTER"; t.size = 0.42
    o = bpy.data.objects.new(f"n{h}", t); bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(BLACK); o.parent = W; o.location = (1.75 * math.cos(a), 1.75 * math.sin(a), 0.525)
for m_ in range(60):
    a = PI / 2 - m_ * PI / 30; L = 0.18 if m_ % 5 == 0 else 0.08
    box(0.03 if m_ % 5 else 0.05, L, 0.01, (2.12 * math.cos(a), 2.12 * math.sin(a), 0.525), BLACK, W, bevel=0, rot=(0, 0, a - PI / 2))
SUB = (0, -1.05)  # 秒のサブダイヤル(6時側) = 4番車の軸
torus(0.5, 0.012, (*SUB, 0.525), BLACK, W)


def hand(name, length, width, tail, m, center, z):
    piv = empty(name, (*center, z), W)
    pts = [(-width * 0.5, -tail), (width * 0.5, -tail), (width * 0.35, length * 0.75), (width * 1.1, length * 0.82),
           (0, length), (-width * 1.1, length * 0.82), (-width * 0.35, length * 0.75)]
    poly(name + "_m", pts, 0.015, m, piv)
    cyl(width * 0.9, 0.03, (0, 0, 0), m, piv, v=16)
    return piv

H_HOUR = hand("hour", 1.15, 0.09, 0.2, BLUE, (0, 0), 0.54)
H_MIN = hand("minute", 1.75, 0.07, 0.25, BLUE, (0, 0), 0.56)
H_SEC = hand("second", 0.45, 0.025, 0.1, BLUE, SUB, 0.54)

# ---------- 前蓋・裏蓋(9時の蝶番) ----------
front = empty("front_lid", (-R, 0, 0.5), W)
cyl(R, 0.08, (R, 0, 0.38), GOLD, front, v=96)
torus(R - 0.05, 0.16, (R, 0, 0.12), GOLD, front, seg=96)
for rr in (0.6, 1.2, 1.8):  # 彫り(同心円)
    torus(rr, 0.02, (R, 0, 0.43), GOLD_M, front, seg=64)
back = empty("back_lid", (-R, 0, -0.5), W)
cyl(R, 0.08, (R, 0, -0.48), GOLD, back, v=96)
torus(R - 0.05, 0.2, (R, 0, -0.22), GOLD, back, seg=96)
torus(1.4, 0.03, (R, 0, -0.53), GOLD_M, back, seg=64)
cyl(0.22, 0.5, (-R, 0, 0), GOLD, W, axis="Y", v=16)  # 蝶番の筒

# ---------- ムーブメント(裏側, z<-0.5) ----------
cyl(2.3, 0.05, (0, 0, -0.53), NICKEL, W, v=96)  # 地板
# 歯車はX軸回りで作るので、ローカルZへ向けるための枠: 枠内(a,b,c) = 時計(X,Y,Z)=(-c,b,a)
GZ = empty("gz", (0, 0, 0), W, rot=(0, -PI / 2, 0))
def gpos(X, Y, Z): return (Z, Y, -X)
def gyz(X, Y): return (Y, -X)

M_ = 0.0175  # モジュール
def r_of(t): return M_ * t / 2
tr = Train("E")
def wheel(name, t, XY, Z, m=GOLD_M, thick=0.04):
    o = gear(name, r_of(t), t, thick, m, gpos(*XY, Z), GZ, hub=max(0.05, r_of(t) * 0.25), dark=DARK)
    tr.add(name, o, t, gyz(*XY)); return o

F_XY = SUB
E_XY = (F_XY[0] + (r_of(80) + r_of(8)) * math.cos(math.radians(40)), F_XY[1] + (r_of(80) + r_of(8)) * math.sin(math.radians(40)))
C_XY = (0.0, 0.0)
# 3番車: 4番車(歯車80のカナ10と噛む)と2番車(80, カナ10と噛む)の両方に届く位置 = 2円の交点
d4, d2 = r_of(75) + r_of(10), r_of(80) + r_of(10)
dd = math.dist(F_XY, C_XY); aa = (d4 ** 2 - d2 ** 2 + dd ** 2) / (2 * dd); hh = math.sqrt(max(0, d4 ** 2 - aa ** 2))
ux, uy = (C_XY[0] - F_XY[0]) / dd, (C_XY[1] - F_XY[1]) / dd
T_XY = (F_XY[0] + aa * ux + hh * uy, F_XY[1] + aa * uy - hh * ux)
if T_XY[0] > 0: T_XY = (F_XY[0] + aa * ux - hh * uy, F_XY[1] + aa * uy + hh * ux)
B_XY = ((r_of(72) + r_of(12)) * math.cos(math.radians(125)), (r_of(72) + r_of(12)) * math.sin(math.radians(125)))
BAL_XY = (1.15, 0.55)

wheel("E", 8, E_XY, -0.62, NICKEL)  # ガンギ車のカナ
esc = wheel("Ew", 15, E_XY, -0.72, NICKEL)  # ガンギ車
wheel("F", 80, F_XY, -0.62)  # 4番車(秒針)
wheel("Fp", 10, F_XY, -0.68, NICKEL)
wheel("T", 75, T_XY, -0.68)  # 3番車
wheel("Tp", 10, T_XY, -0.62, NICKEL)
wheel("C", 80, C_XY, -0.62)  # 2番車(分針)
wheel("Cp", 12, C_XY, -0.58, NICKEL)
wheel("B", 72, B_XY, -0.58)  # 香箱
cyl(r_of(72) * 0.9, 0.2, (*B_XY, -0.72), GOLD_M, W, v=64)  # 香箱の胴
tr.same_axis("E", "Ew")
tr.mesh("E", "F"); tr.same_axis("F", "Fp"); tr.mesh("Fp", "T"); tr.same_axis("T", "Tp")
tr.mesh("Tp", "C"); tr.same_axis("C", "Cp"); tr.mesh("Cp", "B")
for XY in (E_XY, F_XY, T_XY, C_XY):  # ほぞ
    cyl(0.03, 0.4, (*XY, -0.7), NICKEL, W, v=12)

# アンクル: ガンギ車とテンプの間で左右に振れる
ex, ey = BAL_XY[0] - E_XY[0], BAL_XY[1] - E_XY[1]; el = math.hypot(ex, ey); ux2, uy2 = ex / el, ey / el
P_XY = (E_XY[0] + ux2 * 0.42, E_XY[1] + uy2 * 0.42)
pallet = empty("pallet", (*P_XY, -0.76), W, rot=(0, 0, math.atan2(uy2, ux2) - PI / 2))
poly("fork", [(-0.03, -0.05), (0.03, -0.05), (0.03, el - 0.42 - 0.25), (0.07, el - 0.42 - 0.17), (-0.07, el - 0.42 - 0.17),
              (-0.03, el - 0.42 - 0.25)], 0.03, NICKEL, pallet)
poly("anchor", [(-0.32, -0.2), (-0.26, -0.24), (0, -0.06), (0.26, -0.24), (0.32, -0.2), (0, 0.02)], 0.03, NICKEL, pallet)
for sx in (-0.29, 0.29):
    box(0.05, 0.1, 0.035, (sx, -0.27, 0), RUBY, pallet, bevel=0)  # 爪石
cyl(0.04, 0.05, (0, 0, 0), RUBY, pallet, v=12)

# テンプ: 輪・アーム・チラネジ・ヒゲゼンマイ
bal = empty("balance", (*BAL_XY, -0.84), W)
torus(0.6, 0.045, (0, 0, 0), GOLD, bal, seg=64)
for k in range(2):
    box(1.2, 0.06, 0.04, (0, 0, 0), GOLD, bal, bevel=0, rot=(0, 0, k * PI / 2 + PI / 4))
for k in range(14):
    a = 2 * PI * k / 14
    cyl(0.045, 0.06, (0.66 * math.cos(a), 0.66 * math.sin(a), 0), GOLD_M, bal, v=8)
cyl(0.06, 0.12, (0, 0, 0), RUBY, bal, v=12)
cv = bpy.data.curves.new("hair", "CURVE"); cv.dimensions = "3D"; cv.bevel_depth = 0.006
sp = cv.splines.new("POLY"); N = 160; sp.points.add(N - 1)
for i in range(N):
    a = i / N * 2 * PI * 7; rr = 0.08 + 0.3 * i / N
    sp.points[i].co = (rr * math.cos(a), rr * math.sin(a), -0.04, 1)
hair = bpy.data.objects.new("hair", cv); bpy.context.scene.collection.objects.link(hair)
hair.data.materials.append(BLUE); hair.parent = W; hair.location = (*BAL_XY, -0.84)
# テンプ受けとブリッジ
box(0.16, 1.5, 0.04, (BAL_XY[0] + 0.55, BAL_XY[1] - 0.45, -0.95), NICKEL, W, bevel=0.02, rot=(0, 0, 0.6))
cyl(0.07, 0.03, (*BAL_XY, -0.97), RUBY, W, v=12)
box(0.2, 2.2, 0.04, (-0.55, -0.6, -0.8), NICKEL, W, bevel=0.03, rot=(0, 0, -0.5))
for XY in ((-0.1, -1.6), (-1.0, 0.45)):
    cyl(0.07, 0.03, (*XY, -0.84), RUBY, W, v=12)
for XY in ((1.7, -0.6), (-1.6, -1.2), (-0.5, 1.9), (1.8, 1.0)):  # ネジ
    cyl(0.1, 0.06, (*XY, -0.58), DARK, W, v=16)

# ---------- 動き ----------
BPS = 5.0  # 振動/秒 (18,000振動/時)
def t_of(f): return (f - 1) / 24.0
def esc_angle(f):
    """1振動ごとにガンギ車が半歯(12度)進む。進むときは1フレームほどで素早く。"""
    x = t_of(f) * BPS; k = math.floor(x); fr = x - k
    return math.radians(12) * (k + min(1.0, fr / 0.25))
def bal_angle(f): return math.radians(200) * math.sin(2 * PI * (BPS / 2) * t_of(f))
def pallet_angle(f):
    b = bal_angle(f); return math.radians(9) * max(-1.0, min(1.0, b / math.radians(25)))
def crown_x(f): return -0.15 * (seg(f, 8, 12) - seg(f, 14, 20))
def front_angle(f):
    if f < 13: return 0.0
    t = (f - 13) / 24.0  # バネで跳ね上がり、行き過ぎて揺れて止まる
    return -math.radians(100) * (1 - math.exp(-t * 9) * math.cos(t * 22))
def back_angle(f):
    if f < 88: return 0.0
    t = (f - 88) / 24.0
    return math.radians(100) * (1 - math.exp(-t * 9) * math.cos(t * 22))

T0 = (10 * 60 + 9) * 60 + 20  # 10:09:20から
for f in range(1, FEND + 1):
    th = esc_angle(f)
    tr.key(th, f)
    sec_rot = tr.angle("F", th) - tr.angle("F", 0)  # 時計回りで負
    secs = T0 + t_of(f)
    H_SEC.rotation_euler.z = sec_rot - 2 * PI * (T0 % 60) / 60; key_rot(H_SEC, f, 2)
    H_MIN.rotation_euler.z = -2 * PI * (secs % 3600) / 3600; key_rot(H_MIN, f, 2)
    H_HOUR.rotation_euler.z = -2 * PI * (secs % 43200) / 43200; key_rot(H_HOUR, f, 2)
    bal.rotation_euler.z = bal_angle(f); key_rot(bal, f, 2)
    hair.rotation_euler.z = bal_angle(f) * 0.25; key_rot(hair, f, 2)  # ヒゲゼンマイの巻き締め
    pallet.rotation_euler.y = 0; pallet.rotation_euler.z = math.atan2(uy2, ux2) - PI / 2 + pallet_angle(f); key_rot(pallet, f, 2)
    crown.location.x = R + 0.6 + crown_x(f); crown.keyframe_insert("location", index=0, frame=f)
    front.rotation_euler.y = front_angle(f); key_rot(front, f, 1)
    back.rotation_euler.y = back_angle(f); key_rot(back, f, 1)

# ---------- カメラ・光 ----------
WC = (0, 0, 3.15)
camera([
    (1, (5, -13, 6.5), (0.3, 0, 3.0)),
    (14, (6, -11, 5.5), (1.2, 0, 3.1)),
    (34, (2.5, -9.5, 4.6), (0, 0, 3.15)),
    (66, (1.0, -7.2, 3.6), (0, -0.3, 2.6)),
    (90, (8.5, 7.5, 5.0), (0, 0, 3.1)),
    (118, (3.0, 8.5, 4.4), (0.2, 0, 3.2)),
    (144, (1.6, 6.4, 3.9), (0.5, 0, 3.4)),
], lens=55)
area((-8, -10, 14), 2500, 8, (1.0, 0.92, 0.8), WC)
area((10, 8, 9), 1800, 6, (0.75, 0.85, 1.0), WC)
area((3, -6, 2), 300, 4, (1.0, 0.95, 0.9), WC)
area((-4, 8, 3), 500, 4, (1.0, 0.95, 0.9), WC)
world((0.03, 0.03, 0.035))
render(F0, F1, OUT, SAMPLES, FEND)
