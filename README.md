# cloud_render: GitHub Actions上のheadless Blender共通基盤

ローカルにBlenderを起動せず、GitHub Actions上でBlenderをheadless実行(`blender --background --python ...`)するための共通の仕組み。**Blender活用配下のどのスキル/作業からでも呼び出せる**汎用インフラとして、特定のスキルに専属させずここに置く。

もともと[風景3DCG再現スキル](../../../../.claude/skills/風景3DCG再現/SKILL.md)専用に組んだものだが、リトポロジー(`retopo.yml`)やMixamoアニメーション合成(`animate.yml`)など、風景レンダリング以外のジョブもここに追加していく前提で汎用化した。

## 前提

- `gh` CLIが認証済みで、`repo`と`workflow`スコープを持つこと。
  ```bash
  gh auth status  # Token scopes に workflow がなければ:
  gh auth refresh -h github.com -s workflow  # ブラウザでの再認証が必要、ユーザーに実行してもらう
  ```
- クラウド実行用のGitHubリポジトリを1つ再利用する(初回のみ作成)。デフォルトでは`landscape-3d-cloud-pilot`という名前のプライベートリポジトリ(このディレクトリ`cloud_render/`がそのローカルクローン)。名前は風景スキル発祥の名残だが、中身は汎用ジョブの集合体として運用する。既存のリポジトリがあれば`gh api user/repos --jq '.[].name'`等で存在確認してから再利用する。
- Meshy AIのAPIキーは`.env`の`MESHY_API_KEY`(このディレクトリの親`Blender活用/.env`、あるいは`../../../../2_TRPGシナリオ/TRPG活用実験/cocofolia/.env`が原本)。

## ディレクトリ構成とジョブの追加方法

```
cloud_render/
├── .github/workflows/    # ジョブ1つにつきworkflow 1ファイル(workflow_dispatch)
│   ├── render.yml        # 風景3DCG再現専用
│   ├── retopo.yml        # 自動リトポ(QuadriFlow Remesh)
│   ├── animate.yml       # リグ済みベース+Mixamoアニメーションの合成
│   ├── miniature.yml     # 画像にミニチュア(ティルトシフト)フィルター。Blender 5.0.1、結果はReleaseに添付
│   └── infinite_zoom.yml # 無限ズーム絵(入れ子の絵に寄り続けるループ動画)。エントリは scripts/infinite_zoom.py
└── scripts/               # workflowから呼ばれるBlender Pythonエントリスクリプト
    ├── build_scene.py
    ├── retopo_quadriflow.py
    ├── rig_animate.py
    ├── miniature.py       # miniature.yml のエントリ
    └── miniature_nodes.py # ノード定義(原本: 1_アプリ開発/ミニチュアフィルター/build_miniature.py をコピー)
```

新しいジョブを追加する場合:
1. `scripts/`に`blender --background --python`で実行するエントリスクリプトを追加する。
2. `.github/workflows/`に、下記の「使い方」と同じ型(Blenderダウンロード→アセットダウンロード→スクリプト実行→artifact upload)のworkflowファイルを追加する。
3. コミット・pushしてから`gh workflow run`で起動する。

## 使い方(共通の型)

```bash
cd cloud_render
git add <変更したファイル>
git commit -m "..."
git push

gh workflow run <workflow名>.yml -f assets_json='[{"name":"foo.glb","url":"<署名付きURL>"}]'

gh run list -R <owner>/<repo> --workflow=<workflow名>.yml --limit 1
gh run view <run-id> -R <owner>/<repo> --json status,conclusion
gh run download <run-id> -R <owner>/<repo> -n <artifact名> -D <保存先>
```

Mixamoからダウンロードした FBX のように、署名付きURLを持たない小さいバイナリ資産は、`assets_json`経由ではなく`assets/`ディレクトリに直接コミットしてpushしてよい(既存の「スクリプトを都度pushしてから実行する」流儀と同じ)。

## Meshy AIでのモデル生成(人物・クリーチャーを含む)

風景3DCG再現スキルでは有機物(木・岩など)に`image-to-3d`を使っているが、同じAPIでヒューマノイド/クリーチャーも生成できる(`openapi/v1/text-to-3d`または`openapi/v1/image-to-3d`、認証は`Authorization: Bearer $MESHY_API_KEY`、ポーリングで`status: SUCCEEDED`を待ち`model_urls.glb`をダウンロード)。**署名付きURLは発行から約3日で失効するため、ワークフロー実行の直前に取得し直すこと。**

Mixamoの自動リギングを通しやすくするため、プロンプトには以下を含める:
- Tポーズ(腕を横に広げた姿勢)であること
- 単純なヒューマノイド/クリーチャーのプロポーション(極端に手足が長い・体が非対称、等は避ける)
- 単体・シンプルな背景(風景3DCG再現スキルの知見と同じく、背景が複雑だと1メッシュに溶接されることがある)

## 汎用的な既知の落とし穴(風景シーンに限らない、GitHub Actions/Blender共通の罠)

- GitHub Actionsのファイルパスは`/github/workspace`ではなく環境変数`$GITHUB_WORKSPACE`を使う(コンテナ外のubuntu-latestランナーでは前者は存在しない)。
- ワークフローファイルをpushするには`gh`の認証トークンに`workflow`スコープが必要。無いと`refusing to allow an OAuth App to create or update workflow ... without workflow scope`で拒否される。
- ワークフローファイルを初めてpushした直後、`gh workflow run`が`404 workflow not found`になることがある(indexingの遅延と思われる)。何か1行変更してもう一度pushすると解消することを確認済み。
- glTFインポート後、親Empty(軸変換用)のtransformを子に焼き込んでから外し、`transform_apply(scale=True)`でscaleを1.0に正規化する(親のscaleぶん後続計算がズレるのを防ぐ)。風景固有の接地補正ロジックは[風景3DCG再現スキルのtemplates/build_scene_template.py](../../../../.claude/skills/風景3DCG再現/templates/build_scene_template.py)の`import_glb_scaled`を参照。
- Blenderのバージョン間でオペレータ名・引数が変わることがある(特に`quadriflow_remesh`のようなあまり使われないオペレータ)。新しいスクリプトを書く前に`blender --background --python-expr "..."`で対象バージョンでの実在・シグネチャを確認すること。

## retopo_mt.pyについて(使わない理由の記録)

同ディレクトリの親(`Blender活用/retopo_mt.py`)にある対話型リトポロジーアドオンは、**マウスでビューポート上に直接メッシュを描く操作専用**で、`execute()`を持たず`modal()`のみで動作する。GitHub Actionsのheadless実行(`--background`)では3Dビューポートのコンテキストが存在しないため一切呼び出せない。このリポジトリの自動リトポジョブ(`retopo.yml`)ではBlender標準のVoxel Remesh→QuadriFlow Remeshを使う。retopo_mt.pyは削除せず残しているが、ローカルBlender GUIで人間が手作業リトポをしたい場合専用と理解すること。
