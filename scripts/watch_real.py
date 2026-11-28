"""
リアル調の懐中時計(モダン・ハンター: 竜頭12時・蝶番6時、Unitas 6498型の手巻きムーブメント)。
竜頭を押す→前蓋が跳ね開く→秒針が1秒5刻み→裏蓋・中蓋が開く→テンプ往復・ヒゲゼンマイ伸縮・アンクル・ガンギ車・輪列→竜頭を回して角穴車とコハゼが動く。
使い方: blender --background --python watch_real.py -- <start> <end> <outdir> [samples]
出典: リサーチ/2026-11-28_懐中時計ムーブメントの構造_リアル版.md
1BU=1cm。時計ローカル: +Zが文字盤側、+Yが12時(竜頭)、-Yが6時(蝶番・秒針)。裏側(ムーブメント)は-Z。
"""
import bpy, bmesh, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[sys.argv.index("--python") + 1])))
from props_lib import *

F0, F1, OUT, SAMPLES = args()
FEND = 192
FPS = 24
S = reset()
WS = os.environ.get("GITHUB_WORKSPACE", os.getcwd())

# ---------- 素材 ----------
def nodes_of(m):
    nt = m.node_tree; return nt, next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")


def bump_from(m, build, strength=0.3, dist=0.002):
    """build(nt, coord_socket)->高さソケット。法線にバンプとして足す"""
    nt, b = nodes_of(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    h = build(nt, tc.outputs["Object"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = strength; bp.inputs["Distance"].default_value = dist
    nt.links.new(h, bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def M(nt, op, a, b=None, v=None):
    n = nt.nodes.new("ShaderNodeMath"); n.operation = op
    for i, x in enumerate((a, b)):
        if x is None: continue
        if isinstance(x, (int, float)): n.inputs[i].default_value = x
        else: nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def xy(nt, coord):
    s = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(coord, s.inputs[0]); return s.outputs["X"], s.outputs["Y"]


def perlage(nt, coord, cell=0.12, k=55.0):
    """ペルラージュ(円い粒の重なり): セル内の中心からの距離の正弦"""
    x, y = xy(nt, coord)
    fx = M(nt, "SUBTRACT", M(nt, "FRACT", M(nt, "DIVIDE", x, cell)), 0.5)
    fy = M(nt, "SUBTRACT", M(nt, "FRACT", M(nt, "DIVIDE", y, cell)), 0.5)
    d = M(nt, "SQRT", M(nt, "ADD", M(nt, "MULTIPLY", fx, fx), M(nt, "MULTIPLY", fy, fy)))
    return M(nt, "SINE", M(nt, "MULTIPLY", d, k))


def cotes(nt, coord, period=0.22):
    """コート・ド・ジュネーブ(遠い中心からの弧の縞)"""
    x, y = xy(nt, coord)
    dx = M(nt, "ADD", x, 12.0)
    d = M(nt, "SQRT", M(nt, "ADD", M(nt, "MULTIPLY", dx, dx), M(nt, "MULTIPLY", y, y)))
    f = M(nt, "FRACT", M(nt, "DIVIDE", d, period))
    return M(nt, "SINE", M(nt, "MULTIPLY", f, PI))


def guilloche(nt, coord):
    """ギョーシェ(同心円×放射の大麦模様)"""
    x, y = xy(nt, coord)
    r = M(nt, "SQRT", M(nt, "ADD", M(nt, "MULTIPLY", x, x), M(nt, "MULTIPLY", y, y)))
    a = M(nt, "ARCTAN2", y, x)
    w = M(nt, "SINE", M(nt, "ADD", M(nt, "MULTIPLY", r, 40.0), M(nt, "MULTIPLY", M(nt, "SINE", M(nt, "MULTIPLY", a, 36.0)), 1.6)))
    return w


def aniso_radial(m, amount=0.7):
    nt, b = nodes_of(m)
    t = nt.nodes.new("ShaderNodeTangent"); t.direction_type = "RADIAL"; t.axis = "Z"
    for nm in ("Anisotropic", "Specular Anisotropic"):
        if nm in b.inputs: b.inputs[nm].default_value = amount
    nt.links.new(t.outputs[0], b.inputs["Tangent"])
    return m


GOLD = mat("gold18k", (1.0, 0.76, 0.42), metal=1.0, rough=0.16)
GOLD_ENG = bump_from(mat("gold_engraved", (1.0, 0.76, 0.42), metal=1.0, rough=0.2), guilloche, 0.35, 0.004)
GOLD_IN = mat("gold_inner", (0.98, 0.74, 0.42), metal=1.0, rough=0.3)
GILT = aniso_radial(mat("gilt_wheel", (1.0, 0.72, 0.38), metal=1.0, rough=0.28))
PLATE = bump_from(mat("plate_rhodium", (0.82, 0.82, 0.8), metal=1.0, rough=0.33), perlage, 0.25, 0.0015)
BRIDGE = bump_from(mat("bridge_cotes", (0.85, 0.85, 0.83), metal=1.0, rough=0.24), cotes, 0.35, 0.0015)
POLISH = mat("polished_nickel", (0.9, 0.9, 0.88), metal=1.0, rough=0.05)
STEEL = mat("polished_steel", (0.78, 0.79, 0.8), metal=1.0, rough=0.07)
SUNRAY = aniso_radial(mat("sunray_steel", (0.75, 0.76, 0.77), metal=1.0, rough=0.2), 0.9)
BLUE = mat("blued_steel", (0.04, 0.09, 0.42), metal=1.0, rough=0.13)
RUBY = mat("ruby", (0.75, 0.02, 0.06), rough=0.02, transmission=1.0)
nodes_of(RUBY)[1].inputs["IOR"].default_value = 1.76
ENAMEL = mat("enamel", (0.92, 0.9, 0.85), rough=0.08)
INK = mat("ink", (0.015, 0.015, 0.02), rough=0.35)
RED = mat("red_ink", (0.55, 0.03, 0.03), rough=0.35)
GLASS = mat("crystal", (1, 1, 1), rough=0.0, transmission=1.0)
SLOT = mat("slot", (0.0, 0.0, 0.0), rough=0.6)
def _vor(nt, c):
    n = nt.nodes.new("ShaderNodeTexVoronoi"); n.inputs["Scale"].default_value = 9.0
    nt.links.new(c, n.inputs["Vector"]); return n.outputs["Distance"]
LEATHER = bump_from(mat("leather", (0.06, 0.035, 0.022), rough=0.6), _vor, 0.25, 0.01)
WOOD = mat("walnut", (0.17, 0.08, 0.035), rough=0.25, wood=True)

SERIF = None
for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "C:/Windows/Fonts/times.ttf"):
    if os.path.exists(p): SERIF = bpy.data.fonts.load(p); break

# ---------- 便利関数(時計ローカル) ----------
R = 2.5  # ケース半径(50mm)
W = empty("watch", (0, 0, 3.4), rot=(PI / 2, 0, 0))  # ローカル+Y=上、+Z=カメラ(-Y)側


PAR = [W]  # 補助関数の既定の親(ムーブメント部ではMV)


def capsule(p1, p2, w, n=10):
    (x1, y1), (x2, y2) = p1, p2
    a = math.atan2(y2 - y1, x2 - x1); r = w / 2; pts = []
    for i in range(n + 1):
        t = a + PI / 2 + PI * i / n; pts.append((x2 + r * math.cos(t - PI), y2 + r * math.sin(t - PI)))
    for i in range(n + 1):
        t = a + PI / 2 + PI * i / n; pts.append((x1 + r * math.cos(t), y1 + r * math.sin(t)))
    return pts


def disc_pts(c, r, n=40):
    return [(c[0] + r * math.cos(2 * PI * i / n), c[1] + r * math.sin(2 * PI * i / n)) for i in range(n)]


def plate_shape(name, shapes, z, thick, m, edge=POLISH, parent=None):
    """2D形状(点列)の集まりを押し出して重ね、面取りは磨きの素材にする(受けの形)"""
    objs = []
    for i, pts in enumerate(shapes):
        o = poly(f"{name}_{i}", pts, thick, m, parent or PAR[0], loc=(0, 0, z))
        o.data.materials.append(edge)
        bv = o.modifiers.new("bv", "BEVEL"); bv.width = 0.012; bv.segments = 2; bv.material = 1
        bv.limit_method = "ANGLE"
        objs.append(o)
    return objs


def screw(c, z, r=0.055, parent=None, blued=True, ang=0.3):
    s = empty("screw", (c[0], c[1], z), parent or PAR[0], rot=(0, 0, ang))
    sphere(r, (0, 0, 0), BLUE if blued else STEEL, s, scale=(1, 1, 0.45))
    box(r * 2.1, r * 0.28, r * 0.5, (0, 0, -r * 0.35), SLOT, s, bevel=0)  # 溝(裏側=-Zへ向いた頭)
    return s


def jewel(c, z, r=0.075, screws=True):
    """石(ルビー)とゴールドシャトン(受けの上、-Z向き)"""
    cyl(r, 0.025, (c[0], c[1], z), GOLD, PAR[0], v=32)
    sphere(r * 0.45, (c[0], c[1], z - 0.012), RUBY, PAR[0], scale=(1, 1, 0.35))
    if screws:
        for a in (0.6, 0.6 + PI):
            screw((c[0] + r * 1.55 * math.cos(a), c[1] + r * 1.55 * math.sin(a)), z - 0.005, r=0.032, ang=a)


def toothed(name, teeth, r, thick, m, inner=None, club=False, z=0.0, parent=None):
    """XY平面の歯車(Z方向に厚み)。inner>0なら輪(リム)だけ。歯0番が+X(回転0)"""
    bm = bmesh.new(); h = 2 * r / teeth; outer = []
    for k in range(teeth):
        a = 2 * PI * k / teeth; s = PI / teeth
        if club:  # ガンギ車のクラブ歯: 片側が長い斜面
            prof = ((-s * 0.9, r - h * 1.6), (-s * 0.1, r + h * 0.4), (s * 0.35, r + h * 0.4), (s * 0.5, r - h * 0.2), (s * 0.9, r - h * 1.6))
        else:
            prof = ((-s * 0.55, r - h * 0.65), (-s * 0.3, r + h * 0.45), (s * 0.3, r + h * 0.45), (s * 0.55, r - h * 0.65))
        for da, rr in prof:
            outer.append(bm.verts.new((rr * math.cos(a + da), rr * math.sin(a + da), -thick / 2)))
    if inner:
        n = len(outer)
        inn = [bm.verts.new((inner * math.cos(2 * PI * i / n + 0.0001), inner * math.sin(2 * PI * i / n + 0.0001), -thick / 2)) for i in range(n)]
        for i in range(n):
            bm.faces.new((outer[i], outer[(i + 1) % n], inn[(i + 1) % n], inn[i]))
    else:
        bm.faces.new(outer)
    ext = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    bmesh.ops.translate(bm, vec=(0, 0, thick), verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); S.collection.objects.link(o); o.location = (0, 0, z)
    o.data.materials.append(m)
    if parent: o.parent = parent
    return o


def wheel(name, c, z, teeth, r, thick=0.025, spokes=4, m=GILT, pinion=None, pin_z=None, arbor=(None, None)):
    """回る部品の親(空)を返す。リム+スポーク+ハブ(+カナ)+真(ほぞ)"""
    e = empty(name, (c[0], c[1], z), PAR[0])
    rim_in = r * 0.78
    toothed(name + "_rim", teeth, r, thick, m, inner=rim_in, parent=e)
    for k in range(spokes):  # スポークは少し薄く(面の重なりを避ける)
        a = 2 * PI * k / spokes + 0.3
        b = box(rim_in * 1.0, 0.06 * r / 0.5 + 0.02, thick * 0.8, (rim_in * 0.5 * math.cos(a), rim_in * 0.5 * math.sin(a), 0), m, e, bevel=0)
        b.rotation_euler.z = a
    cyl(r * 0.16 + 0.02, thick * 1.3, (0, 0, 0), m, e, v=24)
    if pinion:
        pt, pr = pinion
        toothed(name + "_pinion", pt, pr, 0.04, STEEL, z=(pin_z - z), parent=e)
    if arbor[0] is not None:
        a0, a1 = arbor
        cyl(0.018, abs(a1 - a0), (0, 0, (a0 + a1) / 2 - z), STEEL, e, v=12)
    return e


# ---------- ケース ----------
box(60, 40, 1, (0, 0, -0.5), LEATHER, bevel=0)
box(9, 6, 0.6, (-0.8, 1.0, 0.3), WOOD, bevel=0.15)  # 時計台
cyl(0.12, 7.6, (-3.6, 1.0, 4.4), GOLD_IN)  # 柱(真鍮)
cyl(0.09, 3.7, (-1.8, 1.0, 7.32), GOLD_IN, axis="X")  # 腕
cyl(0.07, 1.3, (0, 0.45, 7.32), GOLD_IN, axis="Y")  # フック
sphere(0.2, (-3.6, 1.0, 8.25), GOLD_IN)

def annulus(name, r_in, r_out, thick, m, parent, z, n=128):
    bm = bmesh.new(); o_ = [bm.verts.new((r_out * math.cos(2 * PI * i / n), r_out * math.sin(2 * PI * i / n), -thick / 2)) for i in range(n)]
    i_ = [bm.verts.new((r_in * math.cos(2 * PI * i / n), r_in * math.sin(2 * PI * i / n), -thick / 2)) for i in range(n)]
    for i in range(n): bm.faces.new((o_[i], o_[(i + 1) % n], i_[(i + 1) % n], i_[i]))
    ext = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    bmesh.ops.translate(bm, vec=(0, 0, thick), verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); S.collection.objects.link(o); o.location = (0, 0, z)
    return fin(o, m, parent)
annulus("case_middle", 2.25, R, 1.0, GOLD, W, 0)  # 胴(筒)
cyl(2.3, 0.04, (0, 0, 0.48), GOLD_IN, W, v=128)  # 文字盤の裏の座
for k in range(160):  # 胴のミル打ち(縦の細い溝)
    a = 2 * PI * k / 160
    box(0.03, 0.03, 0.8, (R * math.cos(a), R * math.sin(a), 0), GOLD, W, bevel=0, rot=(0, 0, a))
torus(R - 0.03, 0.09, (0, 0, 0.47), GOLD, W, seg=128)
torus(R - 0.03, 0.09, (0, 0, -0.47), GOLD, W, seg=128)
cyl(2.34, 0.02, (0, 0, 0.5), ENAMEL, W, v=128)  # 文字盤
# 風防(浅いドーム)
bpy.ops.mesh.primitive_uv_sphere_add(radius=2.36, segments=96, ring_count=48, location=(0, 0, 0.52))
cr = bpy.context.object
bm = bmesh.new(); bm.from_mesh(cr.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.001], context="VERTS"); bm.to_mesh(cr.data); bm.free()
cr.scale = (1, 1, 0.1); fin(cr, GLASS, W)
# 竜頭・リューズ環(12時)
cyl(0.22, 0.42, (0, R + 0.18, 0), GOLD, W, axis="Y", v=32)  # パンダント
crown = empty("crown", (0, R + 0.58, 0), W)
crn = empty("crown_spin", (0, 0, 0), crown)
cyl(0.36, 0.38, (0, 0, 0), GOLD, crn, axis="Y", v=48)
for k in range(30):
    a = 2 * PI * k / 30
    box(0.05, 0.36, 0.06, (0.37 * math.cos(a), 0, 0.37 * math.sin(a)), GOLD, crn, bevel=0, rot=(0, -a, 0))
sphere(0.16, (0, 0.2, 0), GOLD, crn, scale=(1, 0.5, 1))
torus(0.62, 0.08, (0, R + 0.95, 0), GOLD, W, seg=64)  # 環(時計の面内)

# ---------- 文字盤 ----------
def txt(s, size, loc, rot_z, m, font=SERIF, parent=W):
    t = bpy.data.curves.new("t", "FONT"); t.body = s; t.size = size; t.align_x = "CENTER"; t.align_y = "CENTER"
    if font: t.font = font
    t.extrude = 0.002
    o = bpy.data.objects.new("t", t); S.collection.objects.link(o)
    o.data.materials.append(m); o.parent = parent; o.location = loc; o.rotation_euler = (0, 0, rot_z)
    return o

ROMAN = ["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"]
for h in range(12):
    a = PI / 2 - h * PI / 6
    if h == 6: continue  # 6時は秒のサブダイヤル
    txt(ROMAN[h], 0.36, (1.72 * math.cos(a), 1.72 * math.sin(a), 0.515), a - PI / 2, INK)
for m_ in range(60):  # レイルウェイの分目盛
    a = PI / 2 - m_ * PI / 30
    box(0.012 if m_ % 5 else 0.03, 0.12, 0.004, (2.16 * math.cos(a), 2.16 * math.sin(a), 0.512), INK, W, bevel=0, rot=(0, 0, a - PI / 2))
    if m_ % 5 == 0:
        txt(str(m_ if m_ else 60), 0.11, (2.29 * math.cos(a), 2.29 * math.sin(a), 0.515), a - PI / 2, RED, font=None)
torus(2.22, 0.005, (0, 0, 0.511), INK, W, seg=128)
torus(2.1, 0.005, (0, 0, 0.511), INK, W, seg=128)
SUB = (0, -1.05)  # 秒のサブダイヤル(4番車の真)
cyl(0.5, 0.012, (*SUB, 0.508), ENAMEL, W, v=64)  # 一段下げた皿
torus(0.5, 0.008, (*SUB, 0.512), INK, W, seg=64)
for s_ in range(60):
    a = PI / 2 - s_ * PI / 30
    box(0.007, 0.06 if s_ % 5 else 0.09, 0.003, (SUB[0] + 0.43 * math.cos(a), SUB[1] + 0.43 * math.sin(a), 0.515), INK, W, bevel=0, rot=(0, 0, a - PI / 2))
for s_ in (10, 20, 30, 40, 50, 60):
    a = PI / 2 - s_ * PI / 30
    txt(str(s_), 0.08, (SUB[0] + 0.3 * math.cos(a), SUB[1] + 0.3 * math.sin(a), 0.516), 0, INK, font=None)
txt("SWISS MADE", 0.07, (0, -2.0, 0.515), 0, INK, font=None)
txt("Remontoir", 0.13, (0, 0.95, 0.515), 0, INK)


def breguet(name, length, width, center, z, m=BLUE, tail=0.2):
    piv = empty(name, (*center, z), W)
    poly(name + "_shaft", [(-width * 0.5, -tail), (width * 0.5, -tail), (width * 0.3, length * 0.66), (-width * 0.3, length * 0.66)], 0.012, m, piv)
    torus(length * 0.075, width * 0.18, (0, length * 0.72, 0), m, piv)  # ブレゲの月(穴あきの輪)
    poly(name + "_tip", [(-width * 0.3, length * 0.78), (width * 0.3, length * 0.78), (0, length)], 0.012, m, piv)
    cyl(width * 0.9, 0.02, (0, 0, 0), m, piv, v=24)
    return piv

H_HOUR = breguet("hour", 1.2, 0.09, (0, 0), 0.53)
H_MIN = breguet("minute", 1.85, 0.07, (0, 0), 0.55)
H_SEC = empty("second", (*SUB, 0.525), W)
poly("sec_m", [(-0.008, -0.12), (0.008, -0.12), (0.004, 0.42), (-0.004, 0.42)], 0.008, BLUE, H_SEC)
cyl(0.025, 0.02, (0, 0, 0), BLUE, H_SEC, v=16)
cyl(0.05, 0.03, (0, 0, 0.56), BLUE, W, v=16)

# ---------- 前蓋・裏蓋・中蓋(6時の蝶番) ----------
def dome(name, r, h, m, parent, loc, flip=False):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=128, ring_count=48)
    o = bpy.context.object; bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.001], context="VERTS"); bm.to_mesh(o.data); bm.free()
    o.scale = (1, 1, h / r * (-1 if flip else 1)); o.location = loc
    return fin(o, m, parent)

front = empty("front_lid", (0, -R, 0.5), W)
torus(R - 0.04, 0.09, (0, R, 0.06), GOLD, front, seg=128)
dome("front_dome", R - 0.1, 0.45, GOLD_ENG, front, (0, R, 0.0))
torus(0.75, 0.025, (0, R, 0.435), GOLD, front, seg=64)  # 中央の囲み(カルトゥーシュ)
cyl(0.72, 0.01, (0, R, 0.44), GOLD, front, v=64)
back = empty("back_lid", (0, -R, -0.5), W)
torus(R - 0.04, 0.09, (0, R, -0.06), GOLD, back, seg=128)
dome("back_dome", R - 0.1, 0.6, GOLD_ENG, back, (0, R, 0.0), flip=True)
cuv = empty("cuvette", (0, -R + 0.15, -0.55), W)  # 中蓋(ダストカバー)
cyl(R - 0.2, 0.03, (0, R - 0.15, 0.0), GOLD_IN, cuv, v=128)
txt("Remontoir  17 Rubis", 0.16, (0, R - 0.15 + 0.3, -0.018), 0, GOLD, parent=cuv).rotation_euler = (0, PI, 0)
txt("Ancre  Spiral Breguet", 0.13, (0, R - 0.15 - 0.15, -0.018), 0, GOLD, parent=cuv).rotation_euler = (0, PI, 0)
for x in (-0.9, -0.3, 0.3, 0.9):  # 蝶番の節
    cyl(0.12, 0.28, (x, -R - 0.02, 0.5 if x in (-0.9, 0.9) else -0.5), GOLD, W, axis="X", v=24)

# ---------- ムーブメント(裏側) ----------
MV = empty("movement", (0, 0, 0.42), W)  # 胴の中へ
PAR[0] = MV
annulus("mov_ring", 1.84, 2.25, 0.05, GOLD_IN, W, -0.1)  # 胴とムーブメントの間
cyl(1.83, 0.06, (0, 0, -0.52), PLATE, MV, v=128)  # 地板
torus(1.86, 0.035, (0, 0, -0.52), POLISH, MV, seg=128)

# 配置(Unitas 6498型、竜頭12時)。歯車の中心距離はかみ合いから計算
def rr(t, m): return m * t / 2
C = (0.0, 0.0); F = SUB
mC, mT, mF, mE, mB = 0.013, 0.012, 0.0085, 0.0085, 0.017
dCT, dTF = rr(80, mC) + rr(10, mC), rr(75, mT) + rr(10, mT)
dd = math.dist(C, F); aa = (dCT ** 2 - dTF ** 2 + dd ** 2) / (2 * dd); hh = math.sqrt(max(0, dCT ** 2 - aa ** 2))
T = (C[0] + aa * (F[0] - C[0]) / dd + hh, C[1] + aa * (F[1] - C[1]) / dd)  # 右側の交点
assert abs(math.dist(T, C) - dCT) < 1e-6 and abs(math.dist(T, F) - dTF) < 1e-6
dFE = rr(80, mF) + rr(8, mE)
E = (F[0] + dFE * math.cos(math.radians(160)), F[1] + dFE * math.sin(math.radians(160)))
u = (math.cos(math.radians(140)), math.sin(math.radians(140)))
P = (E[0] + 0.30 * u[0], E[1] + 0.30 * u[1])  # アンクル真
B = (E[0] + 0.78 * u[0], E[1] + 0.78 * u[1])  # テンプ真
dBC = rr(80, mB) + rr(12, mB)
A = (dBC * math.cos(math.radians(70)), dBC * math.sin(math.radians(70)))  # 香箱
K = (A[0] + 0.825 * math.cos(math.radians(120)), A[1] + 0.825 * math.sin(math.radians(120)))  # 丸穴車
for p in (A, B, K, T, E, P):
    assert math.hypot(*p) < 1.8, p

tr = Train("E")  # 回転角はローカルZ回り(Trainのyz=ここではxy)
def W_(name, c, z, teeth, r, **kw):
    e = wheel(name, c, z, teeth, r, **kw); tr.add(name, e, teeth, c); return e

# 香箱(ゼンマイの入った太鼓)。歯は上側
barrel = empty("barrel", (*A, -0.66), MV)
cyl(rr(80, mB) * 0.93, 0.14, (0, 0, 0), GILT, barrel, v=96)
toothed("barrel_teeth", 80, rr(80, mB), 0.03, GILT, inner=rr(80, mB) * 0.9, z=-0.055, parent=barrel)
tr.add("A", barrel, 80, A)
W_("C", C, -0.6, 80, rr(80, mC), pinion=(12, rr(12, mB)), pin_z=-0.715, arbor=(-0.55, -0.79))
tr.add("Cp", tr.g["C"][0], 12, C)
W_("T", T, -0.64, 75, rr(75, mT), pinion=(10, rr(10, mC)), pin_z=-0.6, arbor=(-0.55, -0.79))
tr.add("Tp", tr.g["T"][0], 10, T)
W_("F", F, -0.68, 80, rr(80, mF), pinion=(10, rr(10, mT)), pin_z=-0.64, arbor=(-0.55, -0.79))
tr.add("Fp", tr.g["F"][0], 10, F)
esc = empty("E", (*E, -0.72), MV)
toothed("escape_wheel", 15, 0.27, 0.02, STEEL, inner=0.2, club=True, parent=esc)
for k in range(5):
    a = 2 * PI * k / 5
    box(0.2, 0.025, 0.016, (0.1 * math.cos(a), 0.1 * math.sin(a), 0), STEEL, esc, bevel=0, rot=(0, 0, a))
toothed("escape_pinion", 8, rr(8, mE), 0.04, STEEL, z=0.04, parent=esc)
cyl(0.018, 0.24, (0, 0, -0.02), STEEL, esc, v=12)
tr.add("E", esc, 8, E); tr.add("Ew", esc, 15, E)
tr.mesh("E", "F"); tr.same_axis("F", "Fp"); tr.mesh("Fp", "T"); tr.same_axis("T", "Tp")
tr.mesh("Tp", "C"); tr.same_axis("C", "Cp"); tr.mesh("Cp", "A")

# アンクル(アンクル真Pから、テンプ側にフォーク、ガンギ側に2つの爪石)
ang_PB = math.atan2(B[1] - P[1], B[0] - P[0])
pallet = empty("pallet", (*P, -0.735), MV, rot=(0, 0, ang_PB - PI / 2))
L_fork = math.dist(P, B) - 0.13
poly("fork", [(-0.025, 0), (0.025, 0), (0.025, L_fork - 0.06), (0.06, L_fork), (0.035, L_fork + 0.02), (0.012, L_fork - 0.03),
              (-0.012, L_fork - 0.03), (-0.035, L_fork + 0.02), (-0.06, L_fork), (-0.025, L_fork - 0.06)], 0.018, STEEL, pallet)
poly("anchor", [(-0.23, -0.08), (-0.18, -0.13), (0, -0.03), (0.18, -0.13), (0.23, -0.08), (0.04, 0.03), (-0.04, 0.03)], 0.018, STEEL, pallet)
for sx in (-0.19, 0.19):  # 爪石: ガンギ車の中心から0.27(歯先)
    box(0.035, 0.09, 0.022, (sx, -0.11, 0), RUBY, pallet, bevel=0.003, rot=(0, 0, 0.8 if sx < 0 else -0.8))
cyl(0.008, 0.06, (0, L_fork - 0.07, -0.02), STEEL, pallet, v=8)  # ガードピン
cyl(0.03, 0.03, (0, 0, 0), STEEL, pallet, v=16)
cyl(0.014, 0.2, (0, 0, -0.02), STEEL, pallet, v=12)
for sx in (-0.07, 0.07):  # ドテピン(振れ止め)
    cyl(0.012, 0.2, (P[0] + 0.32 * math.cos(ang_PB) + sx * math.cos(ang_PB + PI / 2), P[1] + 0.32 * math.sin(ang_PB) + sx * math.sin(ang_PB + PI / 2), -0.65), STEEL, MV, v=8)

# テンプ(ネジ付きの輪、3本アーム、振り座と振り石)
bal = empty("balance", (*B, -0.79), MV)
toothed("bal_rim", 72, 0.6, 0.04, GOLD, inner=0.55, parent=bal)  # 細かい凹凸の無い輪(歯数=滑らかさ)
for k in range(3):
    a = 2 * PI * k / 3
    box(0.56, 0.05, 0.03, (0.28 * math.cos(a), 0.28 * math.sin(a), 0), GOLD, bal, bevel=0, rot=(0, 0, a))
for k in range(18):  # チラネジ
    a = 2 * PI * k / 18 + 0.1
    e2 = empty("bs", (0.62 * math.cos(a), 0.62 * math.sin(a), 0), bal, rot=(0, 0, a))
    cyl(0.028, 0.06, (0.015, 0, 0), GOLD, e2, axis="X", v=12)
    box(0.004, 0.05, 0.012, (0.046, 0, 0), SLOT, e2, bevel=0)
cyl(0.05, 0.05, (0, 0, 0), STEEL, bal, v=16)
cyl(0.017, 0.3, (0, 0, -0.06), STEEL, bal, v=12)  # 天真
roller_phase = math.atan2(P[1] - B[1], P[0] - B[0])
cyl(0.11, 0.018, (0, 0, 0.055), STEEL, bal, v=32)  # 振り座
cyl(0.012, 0.05, (0.085 * math.cos(roller_phase), 0.085 * math.sin(roller_phase), 0.07), RUBY, bal, v=10)  # 振り石

# ヒゲゼンマイ: 内端は天真と回り、外端は固定。シェイプキーでコイルが詰まる/開く
HS_A = math.radians(270)
cv = bpy.data.curves.new("hairspring", "CURVE"); cv.dimensions = "3D"; cv.bevel_depth = 0.0035; cv.bevel_resolution = 2
sp = cv.splines.new("POLY"); NH = 420; TURNS = 13; R0, R1 = 0.07, 0.38
sp.points.add(NH - 1)
def hs_pt(i, phi):
    s = i / (NH - 1); a = 2 * PI * TURNS * s; rad = R0 + (R1 - R0) * s
    k = 1 - s  # 内側ほど回る
    rad *= 1 - 0.035 * (phi / HS_A) * k * (1 - k) * 4
    return (rad * math.cos(a + phi * k + roller_phase), rad * math.sin(a + phi * k + roller_phase), 0, 1)
for i in range(NH): sp.points[i].co = hs_pt(i, 0)
hair = bpy.data.objects.new("hairspring", cv); S.collection.objects.link(hair)
hair.parent = MV; hair.location = (*B, -0.83); hair.data.materials.append(BLUE)
hair.shape_key_add(name="Basis")
kp = hair.shape_key_add(name="wind"); kp.slider_min = -1.0; kp.slider_max = 1.0
for i in range(NH): kp.data[i].co = hs_pt(i, HS_A)[:3]
cyl(0.035, 0.04, (*B, -0.83), STEEL, MV, v=16)  # コレット
end = hs_pt(NH - 1, 0)
cyl(0.03, 0.08, (B[0] + end[0], B[1] + end[1], -0.86), STEEL, MV, v=12)  # ヒゲ持ち

# ---------- 受け(仕上げ: コート・ド・ジュネーブ、面取りは磨き) ----------
ZB, TB = -0.79, 0.05  # 受けの位置・厚み
# 香箱受け
plate_shape("barrel_bridge", [disc_pts(A, 0.78, 64), capsule(A, (1.25, 1.15), 0.55), capsule(A, (-0.6, 1.45), 0.45),
                              capsule(A, (1.45, 0.15), 0.45)], ZB, TB, BRIDGE)
# 輪列受け(抜き: 腕だけ)
plate_shape("train_bridge", [capsule((1.35, -0.8), T, 0.3), capsule(T, C, 0.26), capsule(T, F, 0.26), capsule(F, (0.75, -1.5), 0.26),
                             disc_pts(C, 0.17), disc_pts(T, 0.15), disc_pts(F, 0.15), capsule(C, (-0.55, 0.35), 0.24)], ZB, TB, BRIDGE)
plate_shape("escape_bridge", [capsule((0.05, -1.62), E, 0.22), disc_pts(E, 0.12)], ZB + 0.01, TB, BRIDGE)
plate_shape("pallet_bridge", [capsule((-0.85, -1.4), P, 0.2), disc_pts(P, 0.11)], -0.752, 0.012, BRIDGE)
# テンプ受け(一段高い)
foot = (-1.45, 0.25)
plate_shape("balance_cock", [disc_pts(foot, 0.32, 40), capsule(foot, B, 0.3), disc_pts(B, 0.22, 48)], -0.9, 0.05, BRIDGE)
cyl(0.3, 0.37, (*foot, -0.69), BRIDGE, MV, v=40)  # 足
for p, z in ((C, ZB - TB / 2), (T, ZB - TB / 2), (F, ZB - TB / 2), (E, ZB + 0.01 - TB / 2), (P, -0.758), (B, -0.925), (A, ZB - TB / 2)):
    if p is A: continue
    jewel(p, z - 0.012, r=0.065 if p is not B else 0.08, screws=p in (C, T, F, B))
# 緩急針(テンプ受けの上): 真で回る針と目盛 + -
reg = empty("regulator", (*B, -0.94), MV, rot=(0, 0, math.atan2(foot[1] - B[1], foot[0] - B[0]) + 0.35))
poly("reg_arm", [(0, -0.03), (0.75, -0.012), (0.8, 0), (0.75, 0.012), (0, 0.03)], 0.012, STEEL, reg)
cyl(0.06, 0.015, (0, 0, 0), STEEL, reg, v=24)
txt("A", 0.09, (foot[0] + 0.25, foot[1] - 0.25, -0.952), 0, INK, font=None).rotation_euler = (0, PI, 0)
txt("R", 0.09, (foot[0] - 0.1, foot[1] - 0.3, -0.952), 0, INK, font=None).rotation_euler = (0, PI, 0)
for p in [(1.25, 1.15), (-0.6, 1.45), (1.45, 0.15), (1.35, -0.8), (0.75, -1.5), (-0.55, 0.35), (0.05, -1.62), (-0.85, -1.4), foot]:
    screw(p, ZB - TB - 0.01 if p != foot else -0.93, r=0.07, ang=hash(p) % 7)

# 角穴車・丸穴車(香箱受けの上、渦巻き仕上げ)とコハゼ
ZR = ZB - TB - 0.02
ratchet = empty("ratchet", (*A, ZR), MV)
toothed("ratchet_t", 48, 0.55, 0.04, SUNRAY, parent=ratchet)
sphere(0.11, (0, 0, -0.02), BLUE, ratchet, scale=(1, 1, 0.4))
box(0.22, 0.03, 0.02, (0, 0, -0.06), SLOT, ratchet, bevel=0)
crownw = empty("crown_wheel", (*K, ZR), MV)
toothed("crown_t", 24, 0.27, 0.04, SUNRAY, parent=crownw)
sphere(0.08, (0, 0, -0.02), BLUE, crownw, scale=(1, 1, 0.4))
for a in (0, 2 * PI / 3, 4 * PI / 3):  # 丸穴車ネジは3本溝(左ネジ)
    box(0.07, 0.012, 0.02, (0.035 * math.cos(a), 0.035 * math.sin(a), -0.045), SLOT, crownw, bevel=0, rot=(0, 0, a))
CA = math.radians(25)  # コハゼの位置(角穴車中心から見た角度)
click_p = (A[0] + 0.72 * math.cos(CA), A[1] + 0.72 * math.sin(CA))
click = empty("click", (*click_p, ZR), MV, rot=(0, 0, CA + PI / 2 + 0.25))
poly("click_m", [(0, -0.05), (0.05, 0), (0.0, 0.05), (-0.28, 0.02), (-0.33, -0.03), (-0.26, -0.03)], 0.03, STEEL, click)
screw(click_p, ZR - 0.03, r=0.05)
poly("click_spring", capsule((click_p[0] + 0.1, click_p[1] - 0.18), (click_p[0] - 0.12, click_p[1] - 0.45), 0.025), 0.02, STEEL, MV, loc=(0, 0, ZR))

# ---------- 動き ----------
BPS = 5.0  # 振動/秒(18,000/時)
def t_of(f): return (f - 1) / FPS
def bal_angle(f): return HS_A * math.sin(2 * PI * (BPS / 2) * t_of(f))
def esc_angle(f):
    """振り石がアンクルを通る(テンプ角0付近)たびに、ガンギ車が12°(半歯)進む"""
    x = t_of(f) * BPS; k = math.floor(x + 0.5); fr = x + 0.5 - k
    return math.radians(12) * (k + min(1.0, max(0.0, (fr - 0.5) / 0.08 + 0.5)))
def pallet_angle(f):
    b = bal_angle(f); return math.radians(8) * max(-1.0, min(1.0, b / math.radians(30)))
def crown_press(f): return -0.14 * (seg(f, 14, 18) - seg(f, 21, 27))
def spring(f, f0, amp):
    if f < f0: return 0.0
    t = (f - f0) / FPS
    return amp * (1 - math.exp(-t * 8) * math.cos(t * 19))
def front_angle(f): return spring(f, 18, math.radians(100))
def back_angle(f): return spring(f, 100, -math.radians(105))
def cuv_angle(f): return -math.radians(95) * seg(f, 116, 136)
def crown_spin(f):  # 巻き上げ: 前後に回す(往路で巻け、復路は空転)
    w = 0.0
    for c0 in (146, 160, 174):
        w += 2.2 * seg(f, c0, c0 + 8) - 2.2 * seg(f, c0 + 8, c0 + 14)
    return w
def wind_amount(f):  # 巻けた量(往路だけ積算)
    return sum(2.2 * seg(f, c0, c0 + 8) for c0 in (146, 160, 174))

T0 = (10 * 3600 + 9 * 60 + 20)
KW = 2 * PI / 48
for f in range(1, FEND + 1):
    th = esc_angle(f)
    for n in ("A", "C", "T", "F", "E"):
        o = tr.g[n][0]; o.rotation_euler.z = tr.angle(n, th); key_rot(o, f, 2)
    sec = T0 + t_of(f)
    H_SEC.rotation_euler.z = (tr.angle("F", th) - tr.angle("F", 0)) - 2 * PI * (T0 % 60) / 60; key_rot(H_SEC, f, 2)
    H_MIN.rotation_euler.z = -2 * PI * (sec % 3600) / 3600; key_rot(H_MIN, f, 2)
    H_HOUR.rotation_euler.z = -2 * PI * (sec % 43200) / 43200; key_rot(H_HOUR, f, 2)
    b = bal_angle(f)
    bal.rotation_euler.z = b; key_rot(bal, f, 2)
    kp.value = b / HS_A; kp.keyframe_insert("value", frame=f)
    pallet.rotation_euler.z = ang_PB - PI / 2 + pallet_angle(f); key_rot(pallet, f, 2)
    crown.location.y = R + 0.58 + crown_press(f); crown.keyframe_insert("location", index=1, frame=f)
    cs = crown_spin(f)
    crn.rotation_euler.y = cs; key_rot(crn, f, 1)
    wa = wind_amount(f)
    crownw.rotation_euler.z = -wa * 16 / 24; key_rot(crownw, f, 2)  # 巻真の小鉄車16→丸穴車24
    ra = wa * 16 / 24 * 24 / 48
    ratchet.rotation_euler.z = ra; key_rot(ratchet, f, 2)
    ph = (ra / KW) % 1.0  # コハゼ: 歯を1枚ずつ乗り越えて落ちる
    click.rotation_euler.z = CA + PI / 2 + 0.25 + 0.18 * ph * (1 if wa > 0 else 0); key_rot(click, f, 2)
    front.rotation_euler.x = front_angle(f); key_rot(front, f, 0)
    back.rotation_euler.x = back_angle(f); key_rot(back, f, 0)
    cuv.rotation_euler.x = cuv_angle(f); key_rot(cuv, f, 0)

# ---------- カメラ・光 ----------
WC = (0, 0, 3.4)
cam = camera([
    (1, (-6.5, -15, 6.5), (0, 0, 4.2)),
    (20, (-3.5, -11.5, 5.5), (0, 0, 4.3)),
    (46, (-1.2, -9.0, 4.0), (0, 0, 3.6)),
    (80, (0.4, -7.0, 2.9), (0.0, -0.5, 2.8)),
    (100, (9.5, -1.0, 5.0), (0, 0, 3.5)),
    (124, (3.5, 9.5, 4.8), (0, 0, 3.4)),
    (146, (0.9, 6.6, 4.4), (0.2, 0.3, 3.9)),
    (170, (-0.3, 5.3, 3.4), (-0.6, 0.3, 3.1)),
    (192, (-0.6, 4.6, 3.0), (-0.9, 0.35, 2.98)),
], lens=60)
cd = cam.data; cd.dof.use_dof = True; cd.dof.aperture_fstop = 1.4
cd.dof.focus_object = next(o for o in S.objects if o.name.startswith("cam_target"))

hdr = os.path.join(WS, "assets", "studio.hdr")
w = bpy.data.worlds.new("w"); S.world = w; w.use_nodes = True; nt = w.node_tree
bg = nt.nodes["Background"]
if os.path.exists(hdr):
    env = nt.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(hdr)
    nt.links.new(env.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = 0.8
else:
    bg.inputs["Color"].default_value = (0.05, 0.05, 0.055, 1)
area((-9, -11, 13), 2200, 8, (1.0, 0.93, 0.83), WC)
area((11, 7, 10), 1400, 6, (0.8, 0.88, 1.0), WC)
area((2, -7, 1.5), 260, 4, (1, 0.97, 0.92), WC)
area((-3, 8, 2.5), 420, 4, (1, 0.97, 0.92), WC)
S.render.use_motion_blur = True; S.render.motion_blur_shutter = 0.5
render(F0, F1, OUT, SAMPLES, FEND)
