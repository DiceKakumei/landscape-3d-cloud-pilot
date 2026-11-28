"""
部品ごとに動く小物(props_*.py / musicbox.py)の共通部品。1BU=1cm。
素材・箱/円柱/歯車・空オブジェクト・カメラ・ライト・描画をまとめる。
"""
import bpy, bmesh, math, os, sys

PI = math.pi


def args():
    """<start> <end> <outdir> [samples]"""
    a = sys.argv[sys.argv.index("--") + 1:]
    return int(a[0]), int(a[1]), a[2], (int(a[3]) if len(a) > 3 else 24)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def sc():
    return bpy.context.scene


# ---------- 素材 ----------
def mat(name, color, metal=0.0, rough=0.5, wood=False, emit=0.0, alpha=1.0, transmission=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*color, 1); b.inputs["Emission Strength"].default_value = emit
    if transmission:
        b.inputs["Transmission Weight"].default_value = transmission; b.inputs["IOR"].default_value = 1.5
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    if wood:  # 木目: 波テクスチャを歪ませて濃淡に
        w = nt.nodes.new("ShaderNodeTexWave"); w.inputs["Scale"].default_value = 1.2
        w.inputs["Distortion"].default_value = 6.0; w.inputs["Detail"].default_value = 3
        r = nt.nodes.new("ShaderNodeValToRGB")
        r.color_ramp.elements[0].color = (color[0] * 0.55, color[1] * 0.5, color[2] * 0.45, 1)
        r.color_ramp.elements[1].color = (*color, 1)
        nt.links.new(w.outputs["Fac"], r.inputs["Fac"]); nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    return m


# ---------- 形 ----------
def fin(o, m, parent=None, smooth=True):
    if m: o.data.materials.append(m)
    if parent: o.parent = parent
    for p in o.data.polygons: p.use_smooth = smooth and len(p.vertices) == 4  # 円柱の蓋(多角形)は平らに
    return o


def box(sx, sy, sz, loc, m, parent=None, bevel=0.05, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot); o = bpy.context.object
    o.scale = (sx, sy, sz); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        bv = o.modifiers.new("bv", "BEVEL"); bv.width = bevel; bv.segments = 2
    return fin(o, m, parent, smooth=False)


AXIS_ROT = {"X": (0, PI / 2, 0), "Y": (PI / 2, 0, 0), "Z": (0, 0, 0)}


def cyl(r, length, loc, m, parent=None, axis="Z", v=48, r2=None):
    """axis向きの円柱(r2を渡すと円錐台)"""
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=length, vertices=v, location=loc, rotation=AXIS_ROT[axis])
    else:
        bpy.ops.mesh.primitive_cone_add(radius1=r, radius2=r2, depth=length, vertices=v, location=loc, rotation=AXIS_ROT[axis])
    return fin(bpy.context.object, m, parent)


def cyl_x(r, length, loc, m, parent=None, v=48):
    return cyl(r, length, loc, m, parent, "X", v)


def torus(R, r, loc, m, parent=None, axis="Z", seg=64):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=seg, minor_segments=12,
                                     location=loc, rotation=AXIS_ROT[axis])
    return fin(bpy.context.object, m, parent)


def sphere(r, loc, m, parent=None, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=32, ring_count=16)
    o = bpy.context.object; o.scale = scale
    return fin(o, m, parent)


def empty(name, loc=(0, 0, 0), parent=None, rot=(0, 0, 0)):
    o = bpy.data.objects.new(name, None); sc().collection.objects.link(o)
    o.location = loc; o.rotation_euler = rot
    if parent: o.parent = parent
    return o


def poly(name, pts2d, thick, m, parent=None, loc=(0, 0, 0)):
    """XY平面の多角形をZ方向にthickだけ押し出した板"""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, -thick / 2)) for x, y in pts2d]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=(0, 0, thick), verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); sc().collection.objects.link(o); o.location = loc
    return fin(o, m, parent, smooth=False)


def gear(name, r, teeth, thick, m, loc, parent=None, hub=0.25, spokes=None, dark=None):
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
    o = bpy.data.objects.new(name, me); sc().collection.objects.link(o); o.location = loc
    o.data.materials.append(m)
    if parent: o.parent = parent
    cyl_x(hub, thick * 1.6, (0, 0, 0), m, o)  # ハブ
    if spokes is None: spokes = r > 0.6
    if spokes:  # 4本スポーク: 暗い円盤の上に棒を渡して抜き穴に見せる
        cyl_x(r * 0.72, thick * 1.02, (0, 0, 0), dark, o)
        for k in range(4):
            b = box(thick * 1.1, r * 1.4, r * 0.14, (0, 0, 0), m, o, bevel=0)
            b.rotation_euler.x = k * PI / 4
    return o


class Train:
    """噛み合う歯車の角度を、基準歯車の回転角θから求める。
    歯車はX軸回り(親の座標系で)。角度0で歯0番が+Y。駆動側の歯が相手方向aを向くとき相手はa+πに歯溝を向ける。"""
    def __init__(self, base):
        self.g = {}; self.phase = {base: 0.0}; self.ratio = {base: 1.0}

    def add(self, name, obj, teeth, yz):
        self.g[name] = (obj, teeth, yz)

    def mesh(self, drv, drn):
        _, td, yd = self.g[drv]; _, tn, yn = self.g[drn]
        a = math.atan2(yn[1] - yd[1], yn[0] - yd[0])
        k = round((a - self.phase[drv]) / (2 * PI / td))
        th_d = self.phase[drv] + k * 2 * PI / td
        self.ratio[drn] = -self.ratio[drv] * td / tn
        th_base = (th_d - self.phase[drv]) / self.ratio[drv]
        self.phase[drn] = (a + PI + PI / tn) - self.ratio[drn] * th_base

    def same_axis(self, a, b):
        self.ratio[b] = self.ratio[a]; self.phase[b] = self.phase[a]

    def angle(self, name, th):
        return self.phase[name] + self.ratio[name] * th

    def key(self, th, f):
        for n, (o, _, _) in self.g.items():
            o.rotation_euler.x = self.angle(n, th); o.keyframe_insert("rotation_euler", index=0, frame=f)


# ---------- 動き ----------
def ease(t):
    t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)


def seg(f, f0, f1):
    """f0→f1で0→1(ease)"""
    return ease((f - f0) / max(1e-6, f1 - f0))


def key_rot(o, f, idx=None):
    o.keyframe_insert("rotation_euler", frame=f) if idx is None else o.keyframe_insert("rotation_euler", index=idx, frame=f)


# ---------- カメラ・光・描画 ----------
def camera(shots, lens=50):
    """shots: [(frame, cam_loc, target_loc), ...] をイーズでつなぐ"""
    s = sc()
    cd = bpy.data.cameras.new("cam"); cd.lens = lens; cd.clip_start = 0.05
    cam = bpy.data.objects.new("cam", cd); s.collection.objects.link(cam); s.camera = cam
    tgt = empty("cam_target")
    tr = cam.constraints.new("TRACK_TO"); tr.target = tgt; tr.track_axis = "TRACK_NEGATIVE_Z"; tr.up_axis = "UP_Y"
    for f, cl, tl in shots:
        cam.location = cl; cam.keyframe_insert("location", frame=f)
        tgt.location = tl; tgt.keyframe_insert("location", frame=f)
    return cam


def area(loc, energy, size, color=(1, 1, 1), target=(0, 0, 0)):
    d = bpy.data.lights.new("a", "AREA"); d.energy = energy; d.size = size; d.color = color
    o = bpy.data.objects.new("a", d); sc().collection.objects.link(o); o.location = loc
    t = o.constraints.new("TRACK_TO"); t.target = empty("lt", target); t.track_axis = "TRACK_NEGATIVE_Z"
    return o


def world(color=(0.02, 0.018, 0.016)):
    w = bpy.data.worlds.new("w"); sc().world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (*color, 1)


def render(F0, F1, OUT, SAMPLES, fend):
    s = sc()
    try: s.render.engine = "CYCLES"
    except TypeError as e: print(e)
    s.cycles.samples = SAMPLES; s.cycles.use_denoising = True
    s.render.resolution_x, s.render.resolution_y = 960, 540
    s.render.fps = 24; s.frame_start, s.frame_end = 1, fend
    s.view_settings.view_transform = "AgX"
    s.render.image_settings.file_format = "PNG"
    os.makedirs(OUT, exist_ok=True)
    for f in range(F0, F1 + 1):
        s.frame_set(f)
        s.render.filepath = os.path.join(OUT, f"f{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    print("done", F0, F1)
