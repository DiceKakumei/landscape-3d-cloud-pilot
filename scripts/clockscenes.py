"""
幻想時計3DCG: Pinterestの4枚(時計×星空)を3DCGで再現する。
使い方: blender --background --python clockscenes.py -- <scene 1-4> <out.png> [preview 0/1]
時計・歯車・柱などの人工物はbpyで直接組み立て、宇宙飛行士だけMeshy glb(assets/astronaut.glb)。
"""
import bpy, bmesh, math, os, sys, random
from mathutils import Vector, Quaternion

argv = sys.argv[sys.argv.index("--") + 1:]
SID = int(argv[0]); OUT = argv[1]; PREVIEW = len(argv) > 2 and argv[2] == "1"
WORKSPACE = os.environ.get("GITHUB_WORKSPACE", os.getcwd())
RES = {1: (720, 1280), 2: (720, 940), 3: (720, 1320), 4: (720, 1280)}[SID]
if PREVIEW:
    RES = (RES[0] // 2, RES[1] // 2)
SAMPLES = 8 if PREVIEW else 40
random.seed(SID * 101)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
R = random.Random(SID)


# ---------- 素材 ----------
def M(name, color=(1, 1, 1), emit=0.0, ecolor=None, metal=0.0, rough=0.5, alpha=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit > 0:
        b.inputs["Emission Color"].default_value = (*(ecolor or color), 1)
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    return m


def starfield(nt, coord, star_scale, neb_scale, base, c1, c2, neb_k, star_k=9.0):
    """星+星雲の色ソケットを返す。coordは座標ソケット。"""
    N = nt.nodes; L = nt.links
    vor = N.new("ShaderNodeTexVoronoi"); vor.feature = "F1"; vor.inputs["Scale"].default_value = star_scale
    L.new(coord, vor.inputs["Vector"])
    rs = N.new("ShaderNodeValToRGB"); rs.color_ramp.elements[0].position = 0.0
    rs.color_ramp.elements[0].color = (star_k, star_k, star_k, 1)
    rs.color_ramp.elements[1].position = 0.035; rs.color_ramp.elements[1].color = (0, 0, 0, 1)
    L.new(vor.outputs["Distance"], rs.inputs["Fac"])
    noi = N.new("ShaderNodeTexNoise"); noi.inputs["Scale"].default_value = neb_scale
    noi.inputs["Detail"].default_value = 8; noi.inputs["Roughness"].default_value = 0.6
    L.new(coord, noi.inputs["Vector"])
    rn = N.new("ShaderNodeValToRGB")
    rn.color_ramp.elements[0].position = 0.4; rn.color_ramp.elements[0].color = (0, 0, 0, 1)
    e = rn.color_ramp.elements.new(0.62); e.color = (*c1, 1)
    rn.color_ramp.elements[2].position = 0.95; rn.color_ramp.elements[2].color = (*c2, 1)
    L.new(noi.outputs["Fac"], rn.inputs["Fac"])
    sc_ = N.new("ShaderNodeVectorMath"); sc_.operation = "SCALE"; sc_.inputs["Scale"].default_value = neb_k
    L.new(rn.outputs["Color"], sc_.inputs[0])
    a1 = N.new("ShaderNodeVectorMath"); a1.operation = "ADD"
    L.new(rs.outputs["Color"], a1.inputs[0]); L.new(sc_.outputs["Vector"], a1.inputs[1])
    a2 = N.new("ShaderNodeVectorMath"); a2.operation = "ADD"; a2.inputs[1].default_value = base
    L.new(a1.outputs["Vector"], a2.inputs[0])
    return a2.outputs["Vector"]


def world(star_scale=260, neb_scale=2.0, base=(0.003, 0.006, 0.03), c1=(0.02, 0.08, 0.6), c2=(0.1, 0.5, 1.0),
          neb_k=1.0, strength=1.0):
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    nt = w.node_tree; nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    col = starfield(nt, tc.outputs["Generated"], star_scale, neb_scale, base, c1, c2, neb_k)
    bg = nt.nodes.new("ShaderNodeBackground"); bg.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(col, bg.inputs["Color"]); nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return w


def star_mat(name, scale, neb_scale, base, c1, c2, neb_k):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    col = starfield(nt, tc.outputs["Object"], scale, neb_scale, base, c1, c2, neb_k, star_k=7.0)
    em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(col, em.inputs["Color"]); nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


# ---------- ジオメトリ ----------
def _fin(o, mat, parent):
    if mat: o.data.materials.append(mat)
    if parent: o.parent = parent
    return o


def torus(Rr, r, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, seg=72, seg2=12):
    bpy.ops.mesh.primitive_torus_add(major_radius=Rr, minor_radius=r, major_segments=seg, minor_segments=seg2,
                                     location=loc, rotation=rot)
    return _fin(bpy.context.active_object, mat, parent)


def cyl(r, d, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, v=48):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, vertices=v, location=loc, rotation=rot)
    return _fin(bpy.context.active_object, mat, parent)


def box(sx, sy, sz, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object; o.scale = (sx, sy, sz)
    return _fin(o, mat, parent)


def sphere(r, loc=(0, 0, 0), mat=None, parent=None, seg=20, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg, ring_count=seg // 2, location=loc)
    o = bpy.context.active_object; o.scale = scale
    return _fin(o, mat, parent)


def empty(loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    o = bpy.data.objects.new("e", None); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = rot; o.scale = (scale,) * 3
    return o


def text(s, size, loc, rot, mat, parent=None, extr=0.02):
    c = bpy.data.curves.new("t", "FONT"); c.body = s; c.size = size; c.extrude = extr
    c.align_x = "CENTER"; c.align_y = "CENTER"
    o = bpy.data.objects.new("t", c); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = rot; o.data.materials.append(mat)
    if parent: o.parent = parent
    return o


def gear(r, teeth, depth, mat, loc=(0, 0, 0), rot=(0, 0, 0), parent=None):
    bm = bmesh.new(); vs = []
    for i in range(teeth * 4):
        a = 2 * math.pi * i / (teeth * 4); rr = r if i % 4 in (1, 2) else r * 0.86
        vs.append(bm.verts.new((math.cos(a) * rr, math.sin(a) * rr, 0)))
    f = bm.faces.new(vs)
    ex = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]:
        v.co.z += depth
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("g"); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("g", me); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = rot; o.data.materials.append(mat)
    if parent: o.parent = parent
    return o


def rock(size, loc, mat, seed):
    rr = random.Random(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=size, location=loc)
    o = bpy.context.active_object
    bm = bmesh.new(); bm.from_mesh(o.data)
    for v in bm.verts:
        v.co *= 1 + rr.uniform(-0.35, 0.35)
    bm.to_mesh(o.data); bm.free()
    o.scale = (rr.uniform(0.6, 1.4), rr.uniform(0.5, 1.2), rr.uniform(0.4, 1.0))
    o.rotation_euler = (rr.uniform(0, 6), rr.uniform(0, 6), rr.uniform(0, 6))
    o.data.materials.append(mat)
    return o


ROMAN = ["XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI"]


def hand(length, width, ang, mat, root, z=0.0):
    c = Vector((math.cos(ang), math.sin(ang), 0)) * length / 2
    box(length, width, width * 0.6, (c.x, c.y, z), (0, 0, ang), mat, root)


def clock(Rr, root, gold, num, hour=-0.6, minute=0.5, face=None, ticks=True):
    torus(Rr, Rr * 0.035, mat=gold, parent=root)
    torus(Rr * 0.8, Rr * 0.012, mat=gold, parent=root)
    for i in range(12):
        a = math.radians(90 - i * 30)
        text(ROMAN[i], Rr * 0.09, (math.cos(a) * Rr * 0.9, math.sin(a) * Rr * 0.9, 0), (0, 0, a - math.pi / 2),
             num, root, Rr * 0.012)
        if ticks:
            for k in range(1, 5):
                b = a - math.radians(6 * k)
                box(Rr * 0.012, Rr * 0.035, Rr * 0.008, (math.cos(b) * Rr * 0.77, math.sin(b) * Rr * 0.77, 0),
                    (0, 0, b), num, root)
    if face:
        cyl(Rr * 0.99, Rr * 0.004, (0, 0, -Rr * 0.01), mat=face, parent=root, v=96)
    hand(Rr * 0.5, Rr * 0.03, hour, gold, root, Rr * 0.02)
    hand(Rr * 0.72, Rr * 0.02, minute, gold, root, Rr * 0.035)
    sphere(Rr * 0.04, (0, 0, Rr * 0.03), gold, root)


def sparkle(loc, size, mat, face_rot):
    e = empty(loc, face_rot)
    sphere(size, (0, 0, 0), mat, e, seg=8, scale=(1, 0.06, 0.06))
    sphere(size, (0, 0, 0), mat, e, seg=8, scale=(0.06, 1, 0.06))
    sphere(size * 0.2, (0, 0, 0), mat, e, seg=8)


def camera(loc, target, lens, roll=0.0):
    cd = bpy.data.cameras.new("c"); cd.lens = lens; cd.clip_end = 2000
    o = bpy.data.objects.new("c", cd); bpy.context.collection.objects.link(o)
    o.location = loc
    q = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y") @ Quaternion((0, 0, 1), roll)
    o.rotation_euler = q.to_euler()
    sc.camera = o
    return o


def area(loc, target, size, energy, color=(1, 1, 1)):
    ld = bpy.data.lights.new("a", "AREA"); ld.energy = energy; ld.size = size; ld.color = color
    o = bpy.data.objects.new("a", ld); bpy.context.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def point(loc, energy, color=(1, 1, 1), radius=0.3):
    ld = bpy.data.lights.new("p", "POINT"); ld.energy = energy; ld.color = color; ld.shadow_soft_size = radius
    o = bpy.data.objects.new("p", ld); bpy.context.collection.objects.link(o); o.location = loc
    return o


# ---------- 素材共通 ----------
GOLD = M("gold", (1.0, 0.68, 0.22), emit=1.6, metal=1.0, rough=0.25)
GOLD_BRIGHT = M("goldb", (1.0, 0.75, 0.3), emit=6.0, metal=1.0, rough=0.3)
CREAM = M("cream", (1, 0.93, 0.7), emit=8.0)
DARKBLUE = M("darkblue", (0.015, 0.03, 0.16), metal=0.6, rough=0.35)


# ================= シーン1: 螺旋に続く時計トンネル =================
def scene1():
    world(star_scale=300, neb_scale=2.5, c1=(0.02, 0.09, 0.7), c2=(0.15, 0.55, 1.0), neb_k=1.3, strength=1.2)
    glass = M("glass", (0.05, 0.15, 0.8), emit=0.5, ecolor=(0.1, 0.3, 1.0), alpha=0.22)
    n = 8
    for i in range(n):
        s = 0.68 ** i
        phi = i * 0.6
        root = empty((math.cos(phi) * 2.2 * s * 2, math.sin(phi) * 2.2 * s * 2, -i * 3.2),
                     (0.38, -0.12, phi * 1.1), scale=s)
        clock(6.0, root, GOLD, GOLD, hour=-0.6 + i * 0.5, minute=0.5 + i * 0.9, face=glass, ticks=(i < 3))
    # 影になる暗い青の腕(螺旋の骨組み)
    for k in range(7):
        t = k * 0.9
        torus(R.uniform(2.5, 9), R.uniform(0.15, 0.4), (R.uniform(-3, 3), R.uniform(-3, 3), -R.uniform(2, 20)),
              (R.uniform(0, 3), R.uniform(0, 3), R.uniform(0, 3)), DARKBLUE, seg=48)
    # 奥の光
    sphere(2.2, (0.4, -0.2, -28), M("core", (0.6, 0.8, 1), emit=60, ecolor=(0.45, 0.7, 1.0)))
    point((0, 0, -22), 20000, (0.4, 0.6, 1.0), 2)
    for k in range(120):  # 星屑
        sphere(0.06, (R.uniform(-9, 9), R.uniform(-9, 9), R.uniform(-30, 5)), M("d", (1, 1, 1), emit=15), seg=6)
    camera((-0.5, -6, 17), (0.2, 0.3, -9), 34, roll=0.08)


# ================= シーン2: 星空の大時計と歯車 =================
def scene2():
    w = world(star_scale=220, neb_scale=3.0, base=(0.01, 0.015, 0.06), c1=(0.1, 0.1, 0.3), c2=(0.5, 0.35, 0.6),
              neb_k=0.5)
    # 地平線に向けて明るく: 世界シェーダに空グラデを重ねる
    nt = w.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.15; mr.inputs["From Max"].default_value = -0.35
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    noi = nt.nodes.new("ShaderNodeTexNoise"); noi.inputs["Scale"].default_value = 3.0; noi.inputs["Detail"].default_value = 6
    nt.links.new(tc.outputs["Generated"], noi.inputs["Vector"])
    cl = nt.nodes.new("ShaderNodeMath"); cl.operation = "MULTIPLY"
    nt.links.new(mr.outputs["Result"], cl.inputs[0]); nt.links.new(noi.outputs["Fac"], cl.inputs[1])
    sky = nt.nodes.new("ShaderNodeBackground"); sky.inputs["Color"].default_value = (1.0, 0.85, 0.6)
    sky.inputs["Strength"].default_value = 2.2
    nt.links.new(mr.outputs["Result"], sky.inputs["Strength"])
    old = [l for l in nt.links if l.to_node.type == "OUTPUT_WORLD"][0]
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(old.from_socket, add.inputs[0]); nt.links.new(sky.outputs["Background"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], old.to_socket)
    dark = M("ring", (0.04, 0.05, 0.09), metal=0.8, rough=0.3)
    silver = M("silver", (0.9, 0.92, 1), emit=3.0)
    root = empty((0, 0, 0), (-0.75, 0.25, 0.35))
    torus(6.2, 0.55, mat=dark, parent=root, seg=96, seg2=16)
    torus(5.4, 0.05, mat=silver, parent=root, seg=96)
    for i in range(12):
        a = math.radians(90 - i * 30)
        text(ROMAN[i], 0.55, (math.cos(a) * 6.2, math.sin(a) * 6.2, 0.58), (0, 0, a - math.pi / 2), silver, root, 0.03)
    for rr, mn in ((4.6, 0.04), (3.4, 0.05), (2.4, 0.04), (1.6, 0.035)):
        torus(rr, mn, (0.3 * (4.6 - rr) / 4.6, 0, 0.15), mat=GOLD_BRIGHT, parent=root, seg=96)
    for k in range(40):  # 環の上の金の粒
        a = R.uniform(0, 6.28); rr = R.choice((4.6, 3.4, 2.4, 1.6))
        sphere(R.uniform(0.07, 0.2), (math.cos(a) * rr, math.sin(a) * rr, 0.15), GOLD_BRIGHT, root, seg=10)
    for (gx, gy, gr, tn) in ((1.7, -1.4, 1.6, 16), (0.4, -2.2, 1.0, 12), (2.9, -0.2, 0.9, 11), (1.0, 0.6, 0.7, 9)):
        gear(gr, tn, 0.18, M("gear", (0.9, 0.75, 0.45), emit=1.2, metal=1.0, rough=0.4), (gx, gy, -0.3), parent=root)
        torus(gr * 0.55, 0.03, (gx, gy, -0.1), mat=GOLD_BRIGHT, parent=root, seg=48)
    hand(2.6, 0.07, 0.9, GOLD_BRIGHT, root, 0.2); hand(3.8, 0.05, 2.35, GOLD_BRIGHT, root, 0.22)
    sphere(0.22, (0, 0, 0.22), GOLD_BRIGHT, root)
    cyl(5.9, 0.02, (0, 0, -0.35), mat=M("face", (0.01, 0.02, 0.06), emit=0.3, ecolor=(0.1, 0.12, 0.3), alpha=0.5), parent=root, v=96)
    # 下へ流れる暗いリボン
    cd = bpy.data.curves.new("rib", "CURVE"); cd.dimensions = "3D"; cd.extrude = 0.9; cd.bevel_depth = 0.08
    sp = cd.splines.new("BEZIER"); sp.bezier_points.add(3)
    pts = [(2.5, 0.5, -5), (4, 1.5, -9), (1, 3.0, -13), (-2.5, 4.0, -17)]
    for p, c in zip(sp.bezier_points, pts):
        p.co = c; p.handle_left_type = p.handle_right_type = "AUTO"
    ro = bpy.data.objects.new("rib", cd); bpy.context.collection.objects.link(ro)
    ro.data.materials.append(M("rib", (0.03, 0.04, 0.09), metal=0.7, rough=0.3))
    ro.rotation_euler = (0, 0, 0.3)
    for k in range(3):
        sparkle((R.uniform(-5, 5), R.uniform(-3, 4), R.uniform(2, 6)), R.uniform(0.5, 1.1), CREAM, (1.2, 0, 0.3))
    for k in range(70):
        sphere(0.05, (R.uniform(-8, 8), R.uniform(-5, 6), R.uniform(-4, 8)), M("d", (1, 0.9, 0.6), emit=20), seg=6)
    area((-4, -8, 6), (0, 0, 0), 8, 400, (0.8, 0.85, 1))
    camera((-1.0, -13, -6.0), (-0.4, 0, 0.2), 32, roll=0.06)


# ================= シーン3: 時の大聖堂(浮遊する時計と瓦礫) =================
def scene3():
    world(star_scale=80, neb_scale=2, base=(0.004, 0.008, 0.03), c1=(0.02, 0.06, 0.25), c2=(0.1, 0.3, 0.7), neb_k=0.4)
    floor = M("floor", (0.02, 0.025, 0.04), metal=0.6, rough=0.12)
    stone = M("stone", (0.06, 0.05, 0.045), rough=0.8)
    cyan = M("cyan", (0.6, 0.95, 1.0), emit=9.0, ecolor=(0.55, 0.9, 1.0))
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 40, 0)); bpy.context.active_object.data.materials.append(floor)
    for j in range(14):  # 左右の柱列
        y = 6 + j * 6
        for sx in (-1, 1):
            box(1.6, 1.6, 15, (sx * 9, y, 7.5), mat=stone)
            box(2.2, 2.2, 0.8, (sx * 9, y, 0.4), mat=stone)
            torus(4.5, 0.5, (sx * 4.5, y, 14.5), (math.pi / 2, 0, 0), stone, seg=32)
            point((sx * 8, y - 1.5, 1.2), 900, (1.0, 0.6, 0.2), 0.4)
    box(30, 100, 1, (0, 50, 16), mat=stone)
    box(1, 100, 15, (-14, 50, 7), mat=stone); box(1, 100, 15, (14, 50, 7), mat=stone)
    # 床の魔法陣
    for rr, mn in ((2.2, 0.04), (3.4, 0.03), (5.5, 0.05), (8, 0.04), (12, 0.05), (18, 0.05)):
        torus(rr, mn, (0, 9, 0.02), mat=cyan, seg=128, seg2=6)
        for k in range(int(rr * 4)):
            a = k / (rr * 4) * 6.28
            text(R.choice("IVXLTMFHNKZYP"), 0.45, (math.cos(a) * (rr + 0.5), 9 + math.sin(a) * (rr + 0.5), 0.03),
                 (0, 0, a - math.pi / 2), cyan, extr=0.01)
    for k in range(10):
        a = k * 0.628
        box(0.04, 4.5, 0.03, (math.cos(a) * 0.1, 9, 0.025), (0, 0, a), cyan)
    # 中央の浮遊する時計(円盤)
    for k in range(46):
        r = R.uniform(0.35, 1.3)
        loc = (R.uniform(-6.5, 6.5), R.uniform(5, 45), R.uniform(2.5, 13))
        root = empty(loc, (R.uniform(0.6, 1.6), R.uniform(-0.8, 0.8), R.uniform(0, 6.28)))
        torus(r, r * 0.07, mat=GOLD, parent=root, seg=40)
        torus(r * 0.78, r * 0.025, mat=cyan, parent=root, seg=40, seg2=6)
        cyl(r * 0.95, 0.04, (0, 0, -0.02), mat=M("dk", (0.01, 0.02, 0.04), emit=0.6, ecolor=(0.1, 0.4, 0.6)), parent=root, v=40)
        for q in range(6):
            box(r * 1.5, r * 0.025, 0.03, (0, 0, 0.01), (0, 0, q * 0.52), cyan, root)
        hand(r * 0.55, r * 0.05, R.uniform(0, 6), cyan, root, 0.03)
        hand(r * 0.8, r * 0.035, R.uniform(0, 6), cyan, root, 0.04)
    for k in range(95):  # 瓦礫
        rock(R.uniform(0.15, 0.7), (R.uniform(-7, 7), R.uniform(3, 45), R.uniform(1.5, 14)), M("rk", (0.07, 0.045, 0.035), rough=0.7), k)
    box(5, 3.5, 0.9, (0.6, 5.5, 0.5), (0, 0, 0.1), stone)  # 床の割れた石板
    rock(2.6, (0.3, 5.0, 0.4), M("slab", (0.09, 0.1, 0.12), rough=0.6), 999).scale = (1.5, 1.0, 0.25)
    for (x, y) in ((-2.4, 3.0), (-0.8, 12), (-1.5, 18), (3.2, 20)):
        bpy.ops.mesh.primitive_cone_add(radius1=0.5, radius2=0.3, depth=1.1, location=(x, y, 0.55), vertices=24)
        bpy.context.active_object.data.materials.append(M("bell", (0.03, 0.04, 0.07), metal=0.8, rough=0.3))
    # 光の柱
    bpy.ops.mesh.primitive_cone_add(radius1=5, radius2=0.5, depth=40, location=(0, 22, 20), vertices=48)
    bpy.context.active_object.data.materials.append(M("beam", (0.4, 0.7, 1), emit=0.25, ecolor=(0.4, 0.7, 1), alpha=0.05))
    area((0, 20, 15), (0, 20, 0), 14, 12000, (0.45, 0.7, 1.0))
    camera((0, -1.5, 1.3), (0, 24, 7.5), 22, roll=0.0)


# ================= シーン4: 巨大時計と宇宙飛行士 =================
def scene4():
    world(star_scale=200, neb_scale=2.0, base=(0.01, 0.01, 0.05), c1=(0.15, 0.05, 0.4), c2=(0.5, 0.2, 0.8), neb_k=0.8)
    face = star_mat("face", 3.0, 1.2, (0.012, 0.015, 0.1), (0.15, 0.1, 0.7), (0.8, 0.3, 0.9), 1.0)
    ivory = M("ivory", (1, 0.95, 0.75), emit=7.0, ecolor=(1.0, 0.93, 0.7))
    root = empty((-9, 24, 12), (math.pi / 2 - 0.2, 0.25, 0.55 + math.pi / 2 - math.pi / 2))
    root.rotation_euler = (math.radians(75), 0, math.radians(-30))
    rim = M("rim", (1, 0.9, 0.85), emit=14.0, ecolor=(1.0, 0.85, 0.9))
    torus(15, 1.4, mat=rim, parent=root, seg=128, seg2=24)
    torus(13.2, 0.18, mat=GOLD_BRIGHT, parent=root, seg=128)
    for i in range(12):
        a = math.radians(90 - i * 30)
        text(ROMAN[i], 2.0, (math.cos(a) * 11.0, math.sin(a) * 11.0, 0), (0, 0, a - math.pi / 2), ivory, root, 0.15)
    cyl(15, 0.1, (0, 0, -0.5), mat=face, parent=root, v=128)
    hand(8.0, 0.55, math.radians(88), ivory, root, 0.2); hand(6.0, 0.7, math.radians(125), ivory, root, 0.3)
    sphere(0.9, (0, 0, 0.3), ivory, root)
    # 右の機械壁
    dk = M("mach", (0.02, 0.03, 0.05), metal=0.7, rough=0.4)
    red = M("red", (1, 0.1, 0.2), emit=14.0); teal = M("teal", (0.2, 0.9, 1), emit=10.0)
    for k in range(60):
        x = R.uniform(4.5, 11); y = R.uniform(8, 22); z = R.uniform(-1, 14)
        box(R.uniform(0.6, 2.2), R.uniform(0.6, 2), R.uniform(0.6, 3), (x, y, z), mat=dk)
        if R.random() < 0.5:
            box(0.5, 0.05, 0.25, (x - 0.9, y - 1.01, z + R.uniform(-0.5, 0.5)), mat=R.choice([red, teal]))
    box(9, 30, 14, (13, 20, 6), mat=dk)
    # 床(段状)
    pink = M("pk", (1, 0.7, 0.9), emit=3.0, ecolor=(1, 0.65, 0.9))
    for k in range(8):
        box(30, 1.2, 0.12 + k * 0.03, (0, -1.5 + k * 1.6, 0.06 + k * 0.015 - 0.5 + 0.5), mat=M("st", (0.02, 0.03, 0.05), metal=0.5, rough=0.25))
        box(30, 0.04, 0.03, (0, -0.9 + k * 1.6, 0.14), mat=teal if k % 2 else pink)
    box(80, 3, 0.05, (0, 30, 0.02), mat=M("hz", (1, 0.7, 0.95), emit=5.0, ecolor=(1, 0.65, 0.95)))
    for k in range(80):
        sphere(R.uniform(0.02, 0.08), (R.uniform(-6, 6), R.uniform(2, 14), R.uniform(0, 12)), M("d", (0.7, 0.8, 1), emit=18), seg=6)
    # 宇宙飛行士(Meshy)
    glb = os.path.join(WORKSPACE, "assets", "astronaut.glb")
    ax, ay = 0.7, 0.0
    if os.path.exists(glb):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=glb)
        new = [o for o in bpy.data.objects if o not in before]
        for o in new:
            if o.parent:
                m = o.matrix_world.copy(); o.parent = None; o.matrix_world = m
        meshes = [o for o in new if o.type == "MESH"]
        for o in new:
            if o.type != "MESH": bpy.data.objects.remove(o)
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes: o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        if len(meshes) > 1: bpy.ops.object.join()
        a = bpy.context.active_object
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        dims = a.dimensions
        s = 1.85 / max(dims.z, 0.001); a.scale = (s, s, s)
        bpy.ops.object.transform_apply(scale=True)
        a.rotation_euler = (0, 0, math.radians(float(os.environ.get("ASTRO_ROT", "180"))))
        bpy.ops.object.transform_apply(rotation=True)
        zs = [(a.matrix_world @ v.co).z for v in a.data.vertices]
        a.location = (ax, ay, -min(zs) + 0.05)
    else:
        print("astronaut.glb missing (Meshy 402), using procedural astronaut")
        suit = M("suit", (0.85, 0.87, 0.92), rough=0.55)
        gray = M("sg", (0.35, 0.37, 0.42), rough=0.6)
        orange = M("so", (0.9, 0.3, 0.1), rough=0.6)
        ar = empty((ax, ay, 0), (0, 0, math.radians(float(os.environ.get("ASTRO_ROT", "180")) - 180)))
        sphere(0.2, (0, 0, 1.65), suit, ar, seg=24)                                  # ヘルメット
        sphere(0.16, (0, -0.07, 1.66), M("vz", (0.02, 0.03, 0.06), metal=0.9, rough=0.1), ar, seg=20, scale=(1, 0.7, 0.8))
        box(0.5, 0.3, 0.55, (0, 0, 1.2), mat=suit, parent=ar)                         # 胴
        box(0.42, 0.22, 0.5, (0, 0.24, 1.25), mat=gray, parent=ar)                    # バックパック
        for sx in (-1, 1):
            cyl(0.08, 0.5, (sx * 0.32, 0, 1.2), (0, math.radians(sx * 8), 0), suit, ar, v=12)   # 腕
            sphere(0.08, (sx * 0.34, 0, 0.93), gray, ar, seg=10)                                # 手袋
            cyl(0.1, 0.55, (sx * 0.12, 0, 0.62), mat=suit, parent=ar, v=12)                     # 脚
            box(0.17, 0.3, 0.14, (sx * 0.12, -0.05, 0.1), mat=gray, parent=ar)                  # ブーツ
        box(0.1, 0.02, 0.1, (0.28, -0.16, 1.3), mat=orange, parent=ar)                          # 肩の印
        ar.scale = (1.0, 1.0, 1.0)
    area((-1, -6, 4), (ax, ay, 1), 6, 500, (1.0, 0.7, 0.95))   # 時計側の縁光
    area((3, -8, 3), (ax, ay, 1), 4, 150, (0.7, 0.8, 1.0))
    camera((0, -8.5, 1.5), (0.8, 0, 5.0), 30, roll=0.0)


{1: scene1, 2: scene2, 3: scene3, 4: scene4}[SID]()

sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True; sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.max_bounces = 4; sc.cycles.use_adaptive_sampling = True
sc.render.resolution_x, sc.render.resolution_y = RES; sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"; sc.render.filepath = OUT
try:
    sc.view_settings.view_transform = "AgX"
except TypeError:
    pass
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.render.render(write_still=True)
print("DONE", OUT)
