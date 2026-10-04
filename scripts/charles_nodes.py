# Blender 5.0 用：ボカロ曲「シャルル」MV風（ペン画の線＋少数色のベタ塗り＋生成りの紙）コンポジットノードグループ「Charles」を作成する
# 使い方：Blenderのテキストエディタで開いて実行 → コンポジターで「Charles」グループを画像ノードとグループ出力の間に挟む
# 参考：MV（https://www.youtube.com/watch?v=TA5OFS_xX0c）の街並みカット。ref/sheet.jpg
#   ・焦げ茶のラフなペン線／・明暗を赤茶・カーキ・生成りの3〜4色にベタ塗り／・紙のざらつき／・四隅の淡いビネット
import bpy


def lin(hexstr):
    """sRGBの#RRGGBBをシーンリニアのRGBAにする"""
    h = hexstr.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return (*c, 1.0)


DEFAULTS = {
    "Exposure": 0.0,        # 入力の明るさ補正(EV)。夜景など暗い写真は+にする
    "Flatten": 5.0,         # 面をならす強さ（Kuwahara半径px。大きいほどベタ塗りっぽい）
    "Deep Point": 0.05,     # この明るさ以下を最暗色（Ink）にする
    "Dark Point": 0.12,     # この明るさ以下を「暗色（赤茶）」にする
    "Light Point": 0.62,    # この明るさ以上を「紙色」にする
    "Color Keep": 0.35,     # 元写真の色をどれだけ残すか（0=完全にパレット色）
    "Line Flatten": 0.0,    # 線を拾う前に面をならす強さ(px)。大きいほど細かいディテールの線が減る
    "Line Blur": 2.0,       # 線を拾う前のぼかし(px)。大きいと線が太く・少なくなる
    "Line Gain": 3.0,       # 線の拾いやすさ
    "Line Threshold": 0.25, # これ以下の弱いエッジは線にしない
    "Line Strength": 0.95,  # 線の濃さ
    "Grain": 0.06,          # 紙のざらつき
    "Vignette": 0.25,       # 四隅の暗さ
    "Ink": lin("#3a3426"),      # 線の色（焦げ茶）
    "Dark": lin("#a8524f"),     # 暗部の色（赤茶）
    "Mid": lin("#c8bb8c"),      # 中間の色（カーキ）
    "Paper": lin("#f2eedb"),    # 明部・紙の色（生成り）
    "BG Color": lin("#e8dcaa"), # 背景の紙の地色（古い和紙の黄ばみ）
    "BG Stain": lin("#b8995c"), # 背景のしみ・日焼けの色
    "BG Mottle": 1.0,          # しみ・むらの強さ（0=無地）
    "BG Fiber": 0.18,           # 和紙の繊維の強さ
    "Shadow Strength": 0.5,     # 接地の影の濃さ（マスク接続時のみ。0=なし）
    "Ground Y": 0.0,            # 被写体が地面に接する高さ（0=下端, 1=上端）
    "Shadow Height": 0.08,      # 影の厚み（被写体を縦につぶす倍率。小さいほど薄い）
    "Shadow Wobble": 45.0,      # 影の揺らぎ(px)。大きいほどふにゃっとした形
    "Shadow Blur": 14.0,        # 影のぼかし(px)
    "Shadow Color": lin("#7a6340"),  # 影の色
}
COLOR_KEYS = ("Ink", "Dark", "Mid", "Paper", "BG Color", "BG Stain", "Shadow Color")


def build(name="Charles", defaults=DEFAULTS):
    old = bpy.data.node_groups.get(name)
    if old:
        bpy.data.node_groups.remove(old)
    g = bpy.data.node_groups.new(name, "CompositorNodeTree")
    it = g.interface

    s = it.new_socket("Image", in_out="INPUT", socket_type="NodeSocketColor")
    s.default_value = (0, 0, 0, 1)
    ranges = {"Exposure": (-3, 4), "Flatten": (0, 30), "Deep Point": (0, 1), "Dark Point": (0, 1), "Light Point": (0, 1),
              "Color Keep": (0, 1), "Line Flatten": (0, 40), "Line Blur": (0, 10), "Line Gain": (0, 30),
              "Line Threshold": (0, 1), "Line Strength": (0, 1), "Grain": (0, 0.5),
              "Vignette": (0, 1), "BG Mottle": (0, 1), "BG Fiber": (0, 1),
              "Shadow Strength": (0, 1), "Ground Y": (0, 1), "Shadow Height": (0.01, 1), "Shadow Blur": (0, 100), "Shadow Wobble": (0, 300)}
    for k, v in defaults.items():
        if k in COLOR_KEYS:
            s = it.new_socket(k, in_out="INPUT", socket_type="NodeSocketColor")
            s.default_value = v
        else:
            s = it.new_socket(k, in_out="INPUT", socket_type="NodeSocketFloat")
            s.default_value = v
            s.min_value, s.max_value = ranges[k]
    # 被写体マスク（白=被写体、黒=背景）。未接続なら全面白＝背景を消さない
    s = it.new_socket("Mask", in_out="INPUT", socket_type="NodeSocketFloat")
    s.default_value = 1.0
    s.min_value, s.max_value = 0.0, 1.0
    for k, v, lo, hi in (("Background Cut", 1.0, 0.0, 1.0), ("Mask Feather", 2.0, 0.0, 30.0)):
        s = it.new_socket(k, in_out="INPUT", socket_type="NodeSocketFloat")
        s.default_value, s.min_value, s.max_value = v, lo, hi
    it.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    it.new_socket("Lines", in_out="OUTPUT", socket_type="NodeSocketFloat")
    it.new_socket("Tone", in_out="OUTPUT", socket_type="NodeSocketFloat")

    N, L = g.nodes, g.links

    def node(t, x, y, **kw):
        n = N.new(t)
        n.location = (x, y)
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def math(op, x, y, a=None, b=None, clamp=False):
        n = node("ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                L.new(v, n.inputs[i])
        return n.outputs[0]

    def mix(x, y, fac, a, b, blend="MIX"):
        n = node("ShaderNodeMix", x, y, data_type="RGBA", blend_type=blend)
        if isinstance(fac, (int, float)):
            n.inputs[0].default_value = fac
        else:
            L.new(fac, n.inputs[0])
        L.new(a, n.inputs[6])
        L.new(b, n.inputs[7])
        return n.outputs[2]

    gi = node("NodeGroupInput", -1800, 0)
    go = node("NodeGroupOutput", 1500, 0)
    I = gi.outputs

    # --- 面をならす（細かい写真のテクスチャを消してベタ塗りにする） ---
    ex = node("CompositorNodeExposure", -1750, 300)
    L.new(I["Image"], ex.inputs["Image"])
    L.new(I["Exposure"], ex.inputs["Exposure"])
    kw = node("CompositorNodeKuwahara", -1550, 300)
    L.new(ex.outputs[0], kw.inputs["Image"])
    L.new(I["Flatten"], kw.inputs["Size"])

    # --- 明るさ(0〜1)を段数でポスタライズ ---
    bw = node("CompositorNodeRGBToBW", -1350, 300)
    L.new(kw.outputs[0], bw.inputs["Image"])
    # リニア輝度を見た目の明るさ(ガンマ補正後)にしてから段分けする
    lum = math("POWER", -1300, 400, math("MAXIMUM", -1300, 450, bw.outputs[0], 0.0), 1 / 2.2)
    # --- 明るさのしきい値で4色にベタ塗り：Ink(最暗)→Dark→Mid→Paper ---
    def edge(x, y, point):
        m = node("ShaderNodeMapRange", x, y, clamp=True)  # 境目だけ±0.02でなめらかにして階段のギザギザを防ぐ
        L.new(lum, m.inputs["Value"])
        L.new(math("SUBTRACT", x - 100, y - 100, point, 0.02), m.inputs["From Min"])
        L.new(math("ADD", x - 100, y - 160, point, 0.02), m.inputs["From Max"])
        return m.outputs["Result"]

    pal = mix(-450, 250, edge(-650, 250, I["Deep Point"]), I["Ink"], I["Dark"])
    pal = mix(-300, 250, edge(-650, 50, I["Dark Point"]), pal, I["Mid"])
    pal = mix(-150, 250, edge(-650, -150, I["Light Point"]), pal, I["Paper"])
    q = lum  # デバッグ用出力

    # --- 元写真の色を少し残す（彩度を落とした写真色をポスタライズして混ぜる） ---
    hs = node("CompositorNodeHueSat", -1350, 550)
    hs.inputs["Hue"].default_value = 0.5
    hs.inputs["Saturation"].default_value = 0.8
    L.new(kw.outputs[0], hs.inputs["Image"])
    ps = node("CompositorNodePosterize", -1150, 550)
    L.new(hs.outputs[0], ps.inputs["Image"])
    ps.inputs["Steps"].default_value = 4
    # 写真色は明るさをパレット側に揃えてから混ぜる（色味だけ借りる）
    ph = mix(-250, 500, 0.5, ps.outputs[0], pal, blend="MIX")
    fill = mix(-50, 300, I["Color Keep"], pal, ph, blend="MIX")

    # --- 線画：ぼかした画像のエッジ（Sobel）を閾値で抜く ---
    lb = node("CompositorNodeBlur", -1550, -300)
    lsz = node("ShaderNodeCombineXYZ", -1700, -380)
    L.new(I["Line Blur"], lsz.inputs[0])
    L.new(I["Line Blur"], lsz.inputs[1])
    lk = node("CompositorNodeKuwahara", -1650, -300)
    L.new(I["Image"], lk.inputs["Image"])
    L.new(I["Line Flatten"], lk.inputs["Size"])
    L.new(lk.outputs[0], lb.inputs["Image"])
    L.new(lsz.outputs[0], lb.inputs["Size"])
    sb = node("CompositorNodeFilter", -1350, -300)
    # Blender 5.0 ではフィルター種別がノードのプロパティでなく入力ソケット（Menu）になった
    ft = sb.inputs["Type"]
    print("filter types:", [i.identifier for i in ft.enum_items] if hasattr(ft, "enum_items") else "n/a")
    ft.default_value = "Sobel"
    L.new(lb.outputs[0], sb.inputs["Image"])
    eb = node("CompositorNodeRGBToBW", -1150, -300)
    L.new(sb.outputs[0], eb.inputs["Image"])
    e = math("MULTIPLY", -950, -300, eb.outputs[0], I["Line Gain"])
    ln = node("ShaderNodeMapRange", -750, -300, clamp=True)
    L.new(e, ln.inputs["Value"])
    L.new(I["Line Threshold"], ln.inputs["From Min"])
    L.new(math("ADD", -850, -420, I["Line Threshold"], 0.25), ln.inputs["From Max"])
    lines = math("MULTIPLY", -550, -300, ln.outputs["Result"], I["Line Strength"], clamp=True)

    ink = mix(200, 100, lines, fill, I["Ink"])

    # --- 紙のざらつき：高周波ノイズをオーバーレイ ---
    co = node("CompositorNodeImageCoordinates", 300, -300)
    L.new(I["Image"], co.inputs[0])
    nz = node("ShaderNodeTexNoise", 500, -300)
    nz.inputs["Scale"].default_value = 900.0
    nz.inputs["Detail"].default_value = 4.0
    L.new(co.outputs["Normalized"], nz.inputs["Vector"])
    ng_ = mix(750, 100, I["Grain"], ink, nz.outputs["Color"], blend="OVERLAY")

    # --- 背景カット：マスクの外は紙色だけにする（線も塗りも消える） ---
    mb = node("CompositorNodeBlur", 700, -900)
    msz = node("ShaderNodeCombineXYZ", 550, -950)
    L.new(I["Mask Feather"], msz.inputs[0])
    L.new(I["Mask Feather"], msz.inputs[1])
    L.new(I["Mask"], mb.inputs["Image"])
    L.new(msz.outputs[0], mb.inputs["Size"])
    # 残す割合 f = 1 - (1 - マスク) * Background Cut
    f = math("SUBTRACT", 900, -900, 1.0, math("MULTIPLY", 800, -900, math("SUBTRACT", 700, -1000, 1.0, mb.outputs[0]), I["Background Cut"]), clamp=True)
    # 背景は古い和紙風：低周波のしみ＋横に引き伸ばしたノイズの繊維
    nm = node("ShaderNodeTexNoise", 500, -450)
    nm.inputs["Scale"].default_value = 2.5
    nm.inputs["Detail"].default_value = 6.0
    nm.inputs["Roughness"].default_value = 0.6
    L.new(co.outputs["Normalized"], nm.inputs["Vector"])
    stain = mix(650, -450, math("MULTIPLY", 560, -520, nm.outputs["Fac"], I["BG Mottle"], clamp=True), I["BG Color"], I["BG Stain"])
    fv = node("ShaderNodeVectorMath", 300, -800, operation="MULTIPLY")
    fv.inputs[1].default_value = (110.0, 70.0, 1.0)
    L.new(co.outputs["Normalized"], fv.inputs[0])
    nf = node("ShaderNodeTexNoise", 500, -800)
    nf.inputs["Scale"].default_value = 1.0
    nf.inputs["Detail"].default_value = 3.0
    L.new(fv.outputs[0], nf.inputs["Vector"])
    bg = mix(800, -450, I["BG Fiber"], stain, nf.outputs["Color"], blend="OVERLAY")
    # --- 接地の影：マスクを縦につぶして地面の高さに置き、ぼかして背景に重ねる ---
    info = node("CompositorNodeImageInfo", 300, -1100)
    L.new(I["Image"], info.inputs["Image"])
    hsep = node("ShaderNodeSeparateXYZ", 450, -1100)
    L.new(info.outputs["Dimensions"], hsep.inputs[0])
    gd = math("MULTIPLY", 600, -1100, math("SUBTRACT", 520, -1100, I["Ground Y"], 0.5), hsep.outputs["Y"])
    sq = node("CompositorNodeScale", 700, -1100)
    sq.inputs["X"].default_value = 1.0
    L.new(I["Mask"], sq.inputs["Image"])
    L.new(I["Shadow Height"], sq.inputs["Y"])
    tr = node("CompositorNodeTranslate", 900, -1100)
    L.new(sq.outputs["Image"], tr.inputs["Image"])
    L.new(math("MULTIPLY", 800, -1200, math("SUBTRACT", 700, -1200, 1.0, I["Shadow Height"]), gd), tr.inputs["Y"])
    # 揺らぎ：ノイズでずらして陽炎のようにふにゃっとさせる
    nw = node("ShaderNodeTexNoise", 900, -1350)
    nw.inputs["Scale"].default_value = 7.0
    nw.inputs["Detail"].default_value = 2.0
    L.new(co.outputs["Normalized"], nw.inputs["Vector"])
    wv = node("ShaderNodeVectorMath", 1050, -1350, operation="SUBTRACT")
    L.new(nw.outputs["Color"], wv.inputs[0])
    wv.inputs[1].default_value = (0.5, 0.5, 0.5)
    dp = node("CompositorNodeDisplace", 1050, -1100)
    L.new(tr.outputs["Image"], dp.inputs["Image"])
    L.new(wv.outputs[0], dp.inputs["Vector"])
    L.new(I["Shadow Wobble"], dp.inputs["X Scale"])
    L.new(math("MULTIPLY", 1000, -1450, I["Shadow Wobble"], 0.4), dp.inputs["Y Scale"])
    shb = node("CompositorNodeBlur", 1250, -1100)
    ssz = node("ShaderNodeCombineXYZ", 1000, -1200)
    L.new(I["Shadow Blur"], ssz.inputs[0])
    L.new(math("MULTIPLY", 950, -1250, I["Shadow Blur"], 0.5), ssz.inputs[1])
    L.new(dp.outputs["Image"], shb.inputs["Image"])
    L.new(ssz.outputs[0], shb.inputs["Size"])
    sh_f = math("MULTIPLY", 1300, -1100, shb.outputs[0], I["Shadow Strength"], clamp=True)
    bg = mix(1500, -450, sh_f, bg, I["Shadow Color"])
    ng_ = mix(950, 100, f, bg, ng_)
    lines = math("MULTIPLY", 950, -300, lines, f)

    # --- ビネット：四隅を紙のやや暗い色に寄せる ---
    vl = node("ShaderNodeVectorMath", 300, -600, operation="LENGTH")
    L.new(co.outputs["Uniform"], vl.inputs[0])
    vr = node("ShaderNodeMapRange", 500, -600, clamp=True)
    vr.inputs["From Min"].default_value = 0.45
    vr.inputs["From Max"].default_value = 1.2
    L.new(vl.outputs["Value"], vr.inputs["Value"])
    vf = math("MULTIPLY", 700, -600, vr.outputs["Result"], I["Vignette"])
    out = mix(1000, 100, vf, ng_, I["Ink"], blend="MIX")

    L.new(out, go.inputs["Image"])
    L.new(lines, go.inputs["Lines"])
    L.new(q, go.inputs["Tone"])
    return g


def setup_scene(image_path, out_path, group_name="Charles", mask_path=None, shift=(0.0, 0.0)):
    sc = bpy.context.scene
    g = bpy.data.node_groups[group_name]
    tree = sc.compositing_node_group
    if tree is None:
        tree = bpy.data.node_groups.new("Charles Comp", "CompositorNodeTree")
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        sc.compositing_node_group = tree
    tree.nodes.clear()
    img = bpy.data.images.load(image_path, check_existing=True)
    ni = tree.nodes.new("CompositorNodeImage"); ni.image = img; ni.location = (-400, 0)
    ng = tree.nodes.new("CompositorNodeGroup"); ng.node_tree = g; ng.location = (-100, 0)
    o = tree.nodes.new("NodeGroupOutput"); o.location = (250, 0)
    v = tree.nodes.new("CompositorNodeViewer"); v.location = (250, -200)
    src = ni.outputs["Image"]
    if shift != (0.0, 0.0):  # 被写体を画面中央に寄せる（画像とマスクを同じだけ平行移動）
        tn = tree.nodes.new("CompositorNodeTranslate"); tn.location = (-250, 100)
        tn.inputs["X"].default_value, tn.inputs["Y"].default_value = shift
        tree.links.new(src, tn.inputs["Image"])
        src = tn.outputs["Image"]
    tree.links.new(src, ng.inputs["Image"])
    if mask_path:  # 被写体マスク画像（白=被写体）を読み込んでグループの Mask に接続
        mimg = bpy.data.images.load(mask_path, check_existing=True)
        mimg.colorspace_settings.name = "Non-Color"
        nm = tree.nodes.new("CompositorNodeImage"); nm.image = mimg; nm.location = (-400, -250)
        bwn = tree.nodes.new("CompositorNodeRGBToBW"); bwn.location = (-250, -250)
        tree.links.new(nm.outputs["Image"], bwn.inputs["Image"])
        mout = bwn.outputs[0]
        if shift != (0.0, 0.0):
            tm = tree.nodes.new("CompositorNodeTranslate"); tm.location = (-100, -250)
            tm.inputs["X"].default_value, tm.inputs["Y"].default_value = shift
            tree.links.new(mout, tm.inputs["Image"])
            mout = tm.outputs["Image"]
        tree.links.new(mout, ng.inputs["Mask"])
    tree.links.new(ng.outputs["Image"], o.inputs["Image"])
    tree.links.new(ng.outputs["Image"], v.inputs[0])
    sc.render.resolution_x, sc.render.resolution_y = img.size
    sc.render.resolution_percentage = 100
    if sc.camera is None:
        cd = bpy.data.cameras.new("CharlesCam")
        cam = bpy.data.objects.new("CharlesCam", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
    sc.render.use_compositing = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = out_path
    return ng


if __name__ == "__main__":
    build()
