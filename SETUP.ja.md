# セットアップ

署名済みのリリースビルドはありません。Xcode でソースからビルドします。自分で進める場合にも、コーディングエージェントに渡す場合にも使えるチェックリストとして書いています。英語版は [SETUP.md](SETUP.md)。

## 1. 前提

- macOS 15.6 (Sequoia) 以降。
- Xcode 26 以降(App Store または developer.apple.com)。macOS SDK を含む。Xcode 26.4 で確認。
- Xcode に追加した Apple ID(Xcode → Settings → Accounts)。無料の Personal Team でローカルビルド・自分の Mac での実行には十分です。
- 文字起こしを使う場合: Apple Silicon、および [uv](https://docs.astral.sh/uv/)(`brew install uv` など)。

## 2. クローン

```sh
git clone https://github.com/GentaAmeku/MeetingRecorder.git
cd MeetingRecorder
```

## 3. 自分の Team ID と bundle identifier を設定する

Xcode プロジェクトに Team ID や bundle identifier は埋め込まれていません。git 管理外の `Local.xcconfig` から読むので、自分の値が git へ入ることはありません。

```sh
cp MeetingRecorder/Configuration/Local.xcconfig.example MeetingRecorder/Configuration/Local.xcconfig
```

`MeetingRecorder/Configuration/Local.xcconfig` を編集:

```
DEVELOPMENT_TEAM = YOUR_TEAM_ID
MEETING_RECORDER_BUNDLE_ID_PREFIX = com.yourname
```

- `DEVELOPMENT_TEAM`: 自分の Apple Developer Team ID。Xcode → Settings → Accounts → (自分の Apple ID) → チーム → 「Team ID」、または developer.apple.com の Membership Details ページで確認できます。空欄のままプロジェクトを開き、Xcode の Signing & Capabilities タブからチームを選ぶことも可能です。
- `MEETING_RECORDER_BUNDLE_ID_PREFIX`: 自分が管理する逆ドメイン形式の prefix(例: `com.yourname`)。3つのターゲットはそれぞれ `<prefix>.MeetingRecorder` / `<prefix>.MeetingRecorderTests` / `<prefix>.MeetingRecorderUITests` になります。

このファイルが無くてもプロジェクトは開けてビルドできます(チーム未設定・prefix は `com.example` のまま)。署名なしビルドや CI には十分ですが、自分の Mac へのインストールには使えません。macOS はマイク/画面収録の許可を bundle identifier + Team ID の組(「designated requirement」)に紐づけるため、**再ビルドのたびに値を変えない**でください。変えると許可を都度取り直すことになります。

## 4. 開いてビルドする

```sh
open MeetingRecorder/MeetingRecorder.xcodeproj
```

**MeetingRecorder** スキームを選び、実行(⌘R)します。初回起動時にマイク・画面収録の権限を聞かれます(手順6参照)。

コマンドラインから(CI でも同じコマンドを使います):

```sh
xcodebuild build \
  -project MeetingRecorder/MeetingRecorder.xcodeproj \
  -scheme MeetingRecorder \
  -configuration Debug \
  -destination 'platform=macOS'
```

メモリ16GB以下の環境では、コマンドラインからビルドする場合は並列度を抑え(`-jobs 4` 以下)、終わったら `DerivedData`/`build/` を削除してください。このプロジェクトの中間生成物は数百MBから数GBになることがあります。

Xcode の UI を毎回使わず再インストールしたい場合は、`scripts/install_app.sh` が Release ビルドを作って `/Applications` へコピーします(必要なら `sudo` を求めます)。

## 5. 文字起こしをセットアップする(任意)

このセクションを飛ばしても録音は使えます。その場合は `mic.wav` / `system.wav` だけが残り、Transcript は作られません。

```sh
cd postprocess
uv sync
```

これで `postprocess/.venv/bin/postprocess` ができます。アプリはこの CLI の場所を自動で見つけます — `scripts/install_app.sh` が(手順4の代わりにこれを使った場合)`uv sync --frozen` を行ったうえでこの絶対パスをビルド設定 `POSTPROCESS_CLI_PATH` として渡し、Info.plist 経由でアプリが読みます。手動で選ぶ画面はありません。

Xcode から直接 Run(⌘R)して開発する場合は `scripts/install_app.sh` を経由しないため CLI の場所が埋め込まれず、そのビルドでは文字起こしが「見つかりません」になります。開発用の抜け道として、**リポジトリの最上位で**次を実行すると、そのビルド(bundle id は手順3の prefix + `.MeetingRecorder`)に限って CLI パスを上書きできます。上書き先が実行できないときは無視され、インストール時に埋め込んだ場所が使われます:

```sh
defaults write <prefix>.MeetingRecorder postprocessCLIPathOverride "$(pwd)/postprocess/.venv/bin/postprocess"
```

上書きをやめるとき:

```sh
defaults delete <prefix>.MeetingRecorder postprocessCLIPathOverride
```

モデル未DLなど実行できない場合は、設定画面とモデルシートの両方でその旨を案内します。

続けて、アプリから **⚙(設定) →「Download Models…」**。以下を取得します:

- **Whisper**(`mlx-community/whisper-large-v3-turbo`、約1.5GB)— 文字起こしに必須。
- **話者分離**(sherpa-onnx の pyannote-segmentation-3.0 + 3D-Speaker ERes2Net、合計約45MB)— 任意。無くても動作し、その場合は相手全員が1人の「Other」(`otherName` を設定していればその呼び名)として扱われます。

各モデルのライセンスは [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) にまとめています。Hugging Face 上の元モデル `pyannote/segmentation-3.0` はログイン・利用条件への同意が必要なゲート付きモデルですが、このアプリは話者分離モデルの取得で Hugging Face に一切アクセスしません — アプリ内DL・下の手動スクリプトのどちらも、同じ重みを ONNX 変換した `sherpa-onnx` 自身の GitHub リリースから取得するため、話者分離に関しては Hugging Face アカウントは不要です。

話者分離モデルだけを手動で取得したい場合(この2ファイルは Hugging Face ログイン不要):

```sh
scripts/download_diarization_models.sh
```

## 6. 権限を許可する

初回の録音と初回の文字起こしで、それぞれ権限を聞かれます:

- **マイク** — 自分の発話用。
- **画面とシステムオーディオの録音** — 会議相手の声(システム音声)用。単一ストリーム構成のため、映像を保存しなくてもこの権限が必須です(無いとマイクも録音できません)。システム設定 → プライバシーとセキュリティ → 画面とシステムオーディオ録音。
- **ファイルとフォルダ ― 書類フォルダ** — これが基本です。アプリや文字起こしの子プロセスが `~/Documents/MeetingRecorder` に初めて触れたときに、macOS が自動でプロンプトを出します。事前の設定は不要です。
- **フルディスクアクセス**(最後の手段。上の書類フォルダの許可を出しても文字起こしが権限エラーで失敗する場合だけ)。保護対象外の普通のフォルダ(デスクトップ・書類・ダウンロード・iCloud Drive などを除く場所)は本来どこでも追加の許可なしにアクセスできるため、これが必要になるのは逆に、`postprocess` の CLI/仮想環境を iCloud Drive のような**別の保護・同期対象の場所の中**に置いていて、書類フォルダの許可では届かない場合です — システム設定 → プライバシーとセキュリティ → フルディスクアクセス → MeetingRecorder を追加。

## 7. 署名なしでビルド・テストする(CI と同じ手順)

```sh
xcodebuild test \
  -project MeetingRecorder/MeetingRecorder.xcodeproj \
  -scheme MeetingRecorder \
  -configuration Debug \
  -destination 'platform=macOS' \
  -only-testing:MeetingRecorderTests \
  CODE_SIGNING_ALLOWED=NO
```

単体テストは、アプリをテストの受け皿(ホスト)として起動します。`Local.xcconfig` を作ってある場合、そのままではホストがあなたの本物の bundle ID で動き、普段使っているアプリの設定に触れることがあります。テストのときは、捨ててよい prefix を指定してください:

```sh
xcodebuild test … MEETING_RECORDER_BUNDLE_ID_PREFIX=com.example.test
```

`-only-testing:MeetingRecorderTests` で単体テストだけを実行します。UI テスト(`MeetingRecorderUITests`)はログイン済みの実 GUI セッションを必要とし、ヘッドレスでは動きません(CI が単体テストだけを回している理由もこれです。`.github/workflows/ci.yml` 参照)。

```sh
cd postprocess
uv run pytest
```

どちらのテストも録音を行わず、モデルも動かさず、事前に済ませた `uv sync`・モデルDL以外のネットワークアクセスも必要ありません。

## 任意: OnCue からの起動

事前設定は不要です。`meetingrecorder://` の URL scheme はアプリを一度ビルド・実行した時点で自動的に登録されます。何をするか・クエリの検証内容は [README.ja.md](README.ja.md) の「任意: OnCue からの起動」を参照してください。

## 任意: 文字起こし後に AI エージェントへ渡す

既定は「なし」で、完全に任意の機能です。何をするか・どんな危険があるかは [README.ja.md](README.ja.md) の「任意: 文字起こし後に AI エージェントへ渡す」を、設定場所はアプリの ⚙ ポップオーバーを参照してください。Orca で開く場合は、作業フォルダをあらかじめ Orca に登録しておく必要があります。
