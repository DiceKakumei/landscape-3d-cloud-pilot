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
    "Steps": 4.0,           # 明暗の段数（ベタ塗りの色数に相当）
    "Dark Point": 0.38,     # この明るさ以下を「暗色（赤茶）」にする
    "Light Point": 0.72,    # この明るさ以上を「紙色」にする
    "Color Keep": 0.35,     # 元写真の色をどれだけ残すか（0=完全にパレット色）
    "Line Blur": 1.2,       # 線を拾う前のぼかし(px)。大きいと線が太く・少なくなる
    "Line Gain": 6.0,       # 線の拾いやすさ
    "Line Threshold": 0.10, # これ以下の弱いエッジは線にしない
    "Line Strength": 0.95,  # 線の濃さ
    "Grain": 0.06,          # 紙のざらつき
    "Vignette": 0.25,       # 四隅の暗さ
    "Ink": lin("#3a3426"),      # 線の色（焦げ茶）
    "Dark": lin("#8f3b41"),     # 暗部の色（赤茶）
    "Mid": lin("#c8bb8c"),      # 中間の色（カーキ）
    "Paper": lin("#f2eedb"),    # 明部・紙の色（生成り）
}
COLOR_KEYS = ("Ink", "Dark", "Mid", "Paper")


def build(name="Charles", defaults=DEFAULTS):
    old = bpy.data.node_groups.get(name)
    if old:
        bpy.data.node_groups.remove(old)
    g = bpy.data.node_groups.new(name, "CompositorNodeTree")
    it = g.interface

    s = it.new_socket("Image", in_out="INPUT", socket_type="NodeSocketColor")
    s.default_value = (0, 0, 0, 1)
    ranges = {"Exposure": (-3, 4), "Flatten": (0, 30), "Steps": (2, 8), "Dark Point": (0, 1), "Light Point": (0, 1),
              "Color Keep": (0, 1), "Line Blur": (0, 10), "Line Gain": (0, 30),
              "Line Threshold": (0, 1), "Line Strength": (0, 1), "Grain": (0, 0.5),
              "Vignette": (0, 1)}
    for k, v in defaults.items():
        if k in COLOR_KEYS:
            s = it.new_socket(k, in_out="INPUT", socket_type="NodeSocketColor")
            s.default_value = v
        else:
            s = it.new_socket(k, in_out="INPUT", socket_type="NodeSocketFloat")
            s.default_value = v
            s.min_value, s.max_value = ranges[k]
    it.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    it.new_socket("Lines", in_out="OUTPUT", socket_type="NodeSocketFloat")

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
    stp = math("MAXIMUM", -1350, 150, I["Steps"], 2.0)
    q = math("DIVIDE", -1000, 250, math("FLOOR", -1150, 250, math("MULTIPLY", -1250, 250, lum, stp)), stp, clamp=True)
    # 最明部を取りこぼさないよう、段の中央に寄せて 0〜1 に再正規化
    q = math("DIVIDE", -850, 250, q, math("SUBTRACT", -1000, 100, 1.0, math("DIVIDE", -1100, 100, 1.0, stp)), clamp=True)

    # --- 3色パレットへマップ：暗(Dark)→中(Mid)→明(Paper) ---
    # t1: Dark Point〜(Dark+Light)/2 で Dark→Mid、t2: 中間点〜Light Point で Mid→Paper
    midp = math("MULTIPLY", -850, 50, math("ADD", -950, 50, I["Dark Point"], I["Light Point"]), 0.5)
    t1 = node("ShaderNodeMapRange", -650, 250, clamp=True)
    L.new(q, t1.inputs["Value"])
    L.new(I["Dark Point"], t1.inputs["From Min"])
    L.new(midp, t1.inputs["From Max"])
    t2 = node("ShaderNodeMapRange", -650, 50, clamp=True)
    L.new(q, t2.inputs["Value"])
    L.new(midp, t2.inputs["From Min"])
    L.new(I["Light Point"], t2.inputs["From Max"])
    # 段数で階段状にした t をさらに2値化気味に（Steps が低いとくっきりした面になる）
    pal = mix(-450, 250, t1.outputs["Result"], I["Dark"], I["Mid"])
    pal = mix(-250, 250, t2.outputs["Result"], pal, I["Paper"])

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
    L.new(I["Image"], lb.inputs["Image"])
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
    return g


def setup_scene(image_path, out_path, group_name="Charles"):
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
    tree.links.new(ni.outputs["Image"], ng.inputs["Image"])
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
