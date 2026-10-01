# Blender 5.0 用：ミニチュア（ティルトシフト）コンポジットノードグループ「Miniature」を作成する
# 使い方：Blenderのテキストエディタで開いて実行 → コンポジターで「Miniature」グループを画像ノードとグループ出力の間に挟む
import bpy

DEFAULTS = {
    "Focus Center": 0.28,   # ピント帯の中心（0=下端, 1=上端）
    "Focus Width": 0.075,   # ピント帯の半幅（シャープに残す範囲）
    # 上下の端でぼけ量を揃えるなら Falloff = 帯の端から画面端までの距離
    #   上: 1 - Center - Width / 下: Center - Width
    "Falloff Top": 0.645,   # 帯の上端から最大ぼけに達するまでの距離（画面高さ比）
    "Falloff Bottom": 0.205,# 帯の下端から最大ぼけに達するまでの距離（画面高さ比）
    "Blur Size": 22.0,      # 最大ぼけ半径(px)
    "Blur Curve": 1.5,      # ぼけの立ち上がり（1=距離に比例, 大きいほど帯付近がなだらか）
    "Plastic": 2.0,         # 細かい質感をならしてプラ模型っぽくする（Kuwahara半径px, 0=なし）
    "Sharpen": 0.6,         # ピント帯の中だけシャープにする量（0=なし）
    "Saturation": 1.45,
    "Contrast": 6.0,
    "Gamma": 1.0,           # 1未満で中間調を明るく
    "Exposure": 0.3,        # 全体の明るさ(EV)
    "Glow": 0.15,           # 明るい部分のにじみ（模型の電飾っぽさ, 0=なし）
    "Vignette": 0.05,       # 四隅の暗さ（0=なし）
}
BLUR_LEVELS = 4  # ぼかしの段数（多いほど滑らかだが重い）


def build(name="Miniature", defaults=DEFAULTS):
    old = bpy.data.node_groups.get(name)
    if old:
        bpy.data.node_groups.remove(old)
    g = bpy.data.node_groups.new(name, "CompositorNodeTree")
    it = g.interface

    s = it.new_socket("Image", in_out="INPUT", socket_type="NodeSocketColor")
    s.default_value = (0, 0, 0, 1)
    ranges = {"Focus Center": (0, 1), "Focus Width": (0, 0.5),
              "Falloff Top": (0.01, 1), "Falloff Bottom": (0.01, 1),
              "Blur Size": (0, 200), "Blur Curve": (0.2, 4), "Saturation": (0, 2),
              "Contrast": (-100, 100), "Gamma": (0.2, 3), "Vignette": (0, 1),
              "Plastic": (0, 30), "Exposure": (-3, 3), "Glow": (0, 2), "Sharpen": (0, 1)}
    for k, v in defaults.items():
        s = it.new_socket(k, in_out="INPUT", socket_type="NodeSocketFloat")
        s.default_value = v
        s.min_value, s.max_value = ranges[k]
    it.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    it.new_socket("Mask", in_out="OUTPUT", socket_type="NodeSocketFloat")

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

    gi = node("NodeGroupInput", -1400, 0)
    go = node("NodeGroupOutput", 900, 0)
    I = gi.outputs

    # --- マスク：ピント帯からの距離を上下それぞれ「帯の端→画面端」で0→1に正規化（上下対称） ---
    co = node("CompositorNodeImageCoordinates", -1150, -400)
    sep = node("ShaderNodeSeparateXYZ", -950, -400)
    L.new(I["Image"], co.inputs[0])
    L.new(co.outputs["Normalized"], sep.inputs[0])
    y, c, w = sep.outputs["Y"], I["Focus Center"], I["Focus Width"]

    # 帯の端からの距離を、上側は Falloff Top・下側は Falloff Bottom の距離で 0→1 に正規化
    d = math("ABSOLUTE", -600, -400, math("SUBTRACT", -780, -400, y, c))
    num = math("SUBTRACT", -420, -400, d, w)
    above = math("GREATER_THAN", -780, -600, y, c)
    fsel = node("ShaderNodeMix", -600, -650, data_type="FLOAT")  # above=0→Bottom, 1→Top
    L.new(above, fsel.inputs["Factor"])
    L.new(I["Falloff Bottom"], fsel.inputs[2])
    L.new(I["Falloff Top"], fsel.inputs[3])
    den = math("MAXIMUM", -420, -600, fsel.outputs[0], 0.001)
    t = math("DIVIDE", -240, -400, num, den, clamp=True)
    t = math("POWER", -60, -400, t, I["Blur Curve"])

    # --- 質感：Kuwaharaで細かいテクスチャをならし、塗装したプラ模型のような面にする ---
    kw = node("CompositorNodeKuwahara", -1350, 200)
    L.new(I["Image"], kw.inputs["Image"])
    L.new(I["Plastic"], kw.inputs["Size"])

    # --- 色：彩度・コントラスト ---
    hs = node("CompositorNodeHueSat", -1150, 200)
    hs.inputs["Hue"].default_value = 0.5
    bc = node("CompositorNodeBrightContrast", -950, 200)
    L.new(kw.outputs[0], hs.inputs["Image"])
    L.new(I["Saturation"], hs.inputs["Saturation"])
    L.new(hs.outputs[0], bc.inputs["Image"])
    L.new(I["Contrast"], bc.inputs["Contrast"])
    gm = node("ShaderNodeGamma", -750, 200)  # Blender 5.0 では Compositor 専用の Gamma ノードが廃止
    L.new(bc.outputs[0], gm.inputs["Color"])
    L.new(I["Gamma"], gm.inputs["Gamma"])
    ex = node("CompositorNodeExposure", -550, 200)
    L.new(gm.outputs[0], ex.inputs["Image"])
    L.new(I["Exposure"], ex.inputs["Exposure"])

    # --- シャープ：ピント帯の中（マスクが黒い所）だけアンシャープマスクで輪郭を立てる ---
    # （FilterノードのSharpenはKuwaharaの平坦部を強調して縞が出るため使わない）
    ub = node("CompositorNodeBlur", -350, 400)
    ub.inputs["Size"].default_value = (2, 2)
    L.new(ex.outputs[0], ub.inputs["Image"])
    diff = node("ShaderNodeMix", -150, 400, data_type="RGBA", blend_type="SUBTRACT", clamp_result=False)
    diff.inputs[0].default_value = 1.0
    L.new(ex.outputs[0], diff.inputs[6])
    L.new(ub.outputs[0], diff.inputs[7])
    sh = node("ShaderNodeMix", 50, 250, data_type="RGBA", blend_type="ADD", clamp_result=False)
    in_focus = math("SUBTRACT", -550, -150, 1.0, t)
    L.new(math("MULTIPLY", -400, -150, in_focus, I["Sharpen"]), sh.inputs[0])
    L.new(ex.outputs[0], sh.inputs[6])
    L.new(diff.outputs[2], sh.inputs[7])

    # --- ぼかし：Defocus（Z入力=ぼけ半径マップ）で連続的に ---
    # CPUコンポジターのDefocusは色の段差（ポスタリゼーション）が出るため使わない。
    # 一定半径のガウスぼかしを BLUR_LEVELS 段作り、マスク t に応じて隣り合う段を線形に混ぜる
    s = math("MULTIPLY", 150, -400, t, BLUR_LEVELS)
    result = sh.outputs[2]
    for i in range(1, BLUR_LEVELS + 1):
        rad = math("MULTIPLY", 150, -550 - 60 * i, I["Blur Size"], i / BLUR_LEVELS)
        vec = node("ShaderNodeCombineXYZ", 200, -550 - 60 * i)
        L.new(rad, vec.inputs[0])
        L.new(rad, vec.inputs[1])
        df = node("CompositorNodeBlur", 250, 300 - 180 * i)
        L.new(sh.outputs[2], df.inputs["Image"])
        L.new(vec.outputs[0], df.inputs["Size"])
        w = math("SUBTRACT", 330, -550 - 60 * i, s, i - 1, clamp=True)
        mx = node("ShaderNodeMix", 450 + 40 * i, 300 - 180 * i, data_type="RGBA")
        L.new(w, mx.inputs[0])
        L.new(result, mx.inputs[6])
        L.new(df.outputs[0], mx.inputs[7])
        result = mx.outputs[2]

    # --- にじみ：明るい部分をBloomで光らせる（模型の電飾っぽさ） ---
    gl = node("CompositorNodeGlare", 750, 100)
    gl.inputs["Type"].default_value = "Bloom"
    gl.inputs["Threshold"].default_value = 0.75
    gl.inputs["Size"].default_value = 0.6
    L.new(result, gl.inputs["Image"])
    L.new(I["Glow"], gl.inputs["Strength"])

    # --- ビネット：中心からの距離で四隅を黒に寄せる ---
    vl = node("ShaderNodeVectorMath", -950, -900, operation="LENGTH")
    L.new(co.outputs["Uniform"], vl.inputs[0])
    vr = node("ShaderNodeMapRange", -750, -900, clamp=True)
    vr.inputs["From Min"].default_value = 0.4
    vr.inputs["From Max"].default_value = 1.15
    L.new(vl.outputs["Value"], vr.inputs["Value"])
    vf = math("MULTIPLY", -550, -900, vr.outputs["Result"], I["Vignette"])
    vm = node("ShaderNodeMix", 700, 100, data_type="RGBA")
    vm.inputs[7].default_value = (0, 0, 0, 1)
    L.new(vf, vm.inputs[0])
    L.new(gl.outputs["Image"], vm.inputs[6])

    L.new(vm.outputs[2], go.inputs["Image"])
    L.new(t, go.inputs["Mask"])
    return g


def setup_scene(image_path, out_path, group_name="Miniature"):
    sc = bpy.context.scene
    g = bpy.data.node_groups[group_name]
    tree = sc.compositing_node_group
    if tree is None:
        tree = bpy.data.node_groups.new("Miniature Comp", "CompositorNodeTree")
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
        cd = bpy.data.cameras.new("MiniCam")
        cam = bpy.data.objects.new("MiniCam", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
    sc.render.use_compositing = True
    # 写真の色をそのまま扱う（Blender 5.0 既定の AgX だと暗く濁る）
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = out_path
    return ng
