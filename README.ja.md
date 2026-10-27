# MeetingRecorder

[English](README.md) | 日本語

**メモを取らなくても会議の記録が残る。しかも音声は1秒もクラウドに送らない。**

<p align="center">
  <img src="assets/main-window.png" alt="MeetingRecorder のメイン画面。会議名、相手の名前(任意)、Start Recording のボタンがある" width="600">
</p>

オンライン会議(Google Meet / Zoom / Teams など)を録音し、**この Mac だけで**文字起こし・話者分離する macOS アプリです。明示的にオンにした機能を除き、どこにも送信しません。

自分のマイク音声と会議相手のシステム音声を**別々の WAV** で同期録音し、後処理で「自分/相手」を区別した Transcript にします。録音・文字起こしはクラウドへ送らず、この Mac 上で完結します。Transcript の生成後、元の WAV は既定で自動削除します(設定で保持も可能)。

## なぜ MeetingRecorder か

**MeetingRecorder がないと困ること**

- 会議中にメモを取ると、話に集中できない。取らないと、決まったことや誰が何を引き受けたかを後で思い出せない
- 録音・文字起こしのサービスの多くは音声をクラウドへ送るので、社外秘の会議や取引先との会議では使えない(使ってよいか判断に迷う)
- 1本にまとめた録音から文字起こしすると、誰が話したかが分からなくなる。自分の発言と相手の発言が混ざる
- 録音ファイルが溜まって容量を圧迫し、もう要らない会議の音声がいつまでも残る
- 文字起こしを AI に渡して要約やタスクにしたくても、道具ごとに形式が違い、手で整える必要がある

**MeetingRecorder が解決すること**

- ワンクリックで録音を始められる。[OnCue](https://github.com/GentaAmeku/OnCue) から開けば、会議名と相手の名前も自動で入る
- 自分のマイクと会議の音声を別々に録るので、文字起こしで「どちらが話したか」を取り違えない
- 文字起こし(MLX Whisper)と話者分離(sherpa-onnx)はこの Mac の中で行う。音声は外に出ない
- 「自分/相手A/相手B」(既定の呼び名は Me / Other A / Other B)に分かれた会話ログ(Markdown と JSON)と、全会議の索引ができ、そのまま AI エージェントに渡せる
- 文字起こしが保存されると、元の音声は既定で自動的に消える。残るのは文字だけ
- 文字起こしのあとに Claude Code / Codex へ自動で渡せるので、要約や整理をエージェントに任せられる

## 仕組み

<p align="center">
  <img src="assets/architecture.png" alt="仕組みの図。MeetingRecorder が ScreenCaptureKit でマイクとシステム音声を2つの WAV に録り、停止後に postprocess CLI が MLX Whisper と sherpa-onnx で transcript.md・transcript.json・index.json を作る。ここまではすべて Mac の中。任意で OnCue が会議の情報を渡し、Claude Code か Codex が文字起こしの場所を受け取る">
</p>

録音・文字起こし・話者分離は、すべて「Stays on your Mac」の枠の中で行います。枠の外に出るのは、任意の AI エージェントへの引き継ぎだけです。図は [Archify](https://github.com/tt-a1i/archify) で [`assets/architecture.archify.json`](assets/architecture.archify.json) から作っています。

## 録音する前に

- **同意を取ってください。** 会議、特に相手を録音することは、自分や相手の所在地によって同意が必要な場合があります。通話に適用される録音同意の法律は国や地域(米国では州)によって大きく異なり、このプロジェクトはどの法律が適用されるかを判断できません。迷ったら、通話の全員に先に確認してください。
- **これは個人向けツールであり、コンプライアンス製品ではありません。** 組織的な保持ポリシー、同意記録機能、監査ログはありません。それらが必要な会議に、自分で運用を補わずに使わないでください。

## できること

### 録音

- 自分のマイク音声を `mic.wav`、Mac のシステム音声(会議相手の声)を `system.wav` に**別ファイルで同時録音**(ScreenCaptureKit の単一ストリームで同期)。
- メニューバーまたはメインウィンドウから開始/停止と状態確認。
- 録音前に会議名・相手の名前を任意入力(保存フォルダ名や Transcript に反映)。
- 発言が2分ないと録音を自動停止(任意)。音量ではなく発話検知で判定するため、タイピング音などでは止まらず、初回の発話を検知するまでは監視を始めません。

### ローカルでの文字起こし・話者分離

- 録音停止後、常に**ローカルの MLX Whisper** で自動的に文字起こし(初回はモデルのダウンロードが必要)。モデル未DLなど実行できないときは、その旨を画面で案内します。
- 自分/相手を区別した会話ログ `transcript.md`(`[MM:SS] Me: …` / `[MM:SS] Other: …`)と、構造化された `transcript.json` を出力。
- **両 Transcript の保存に成功すると、入力の `mic.wav` / `system.wav` を既定で自動削除**します。設定の「Keep the original audio files」をオンにすると保持できます。これは意図した設計です — 録音の実体ではなく、そこから作った Transcript が残っていれば十分、という考え方です。
- 会議相手が複数いる場合は **sherpa-onnx で話者分離**し、「Other A / Other B …」に振り分けます。
- 全セッションのカタログ `index.json` を自動生成し、AI エージェントや自分が横断検索できるようにします。
- **文字起こしの言語**: 設定に「Transcription language」の選択(Auto-detect / English / Japanese)があります。既定は Auto-detect で、MLX Whisper に話されている言語を自動判定させます。選ぶと `postprocess-config.json`(`transcript.language`)に書き込まれ、`postprocess` CLI を手元で実行したときもこの値をそのまま読みます。
- **話者の呼び名**: Transcript では自分を "Me"、相手を "Other"(複数いる場合は "Other A" / "Other B" …)と呼びます。ただし録音開始時に相手の名前を入力した場合はその実名を使います。どちらの既定名も、以後生成する Transcript すべてに対して `postprocess-config.json` の `transcript.selfName` / `transcript.otherName` で変更できます。相手が複数いるときは呼び名の後ろに A / B … が付きます。呼び名が日本語で終わる場合は「相手A」のように空白なしでつなぎます。
- **単語の辞書**: 会議で使う語(製品名・技術用語・人の名前)と、その聞き違いの形を辞書に書いておくと、Transcript でその語を自分の書く表記で出します(クロードコードではなく Claude Code)。語は文字にする前に Whisper へヒント(前置きの文)として渡し、それでも残った聞き違いは文字にしたあとで直します。相手の名前と会議名もヒントに入れます。辞書の形は、同じ作者の音声入力アプリ [Tsuzuri](https://github.com/GentaAmeku/Tsuzuri) と同じです。Tsuzuri を入れていれば、その辞書を自動で読みます(書き換えはしません)。ふだんの音声入力で足した語が、会議の文字起こしにも効きます。辞書が無ければ、これまでどおりに文字にします。詳しくは [postprocess/README.md](postprocess/README.md#word-dictionary)。
- **設定ファイルの例**(`~/Documents/MeetingRecorder/postprocess-config.json`):

  ```json
  {
    "schemaVersion": 1,
    "transcript": {
      "selfName": "山田",
      "otherName": "相手",
      "language": "ja"
    },
    "dictionary": {
      "path": "~/Library/Application Support/Tsuzuri/dictionary.json"
    }
  }
  ```

  - `selfName`: 自分の呼び名(既定 `Me`)。空・改行入り・文字列以外は既定に戻ります。
  - `otherName`: 相手の呼び名の元(既定 `Other`)。
  - `language`: 文字起こしの言語。`auto`(既定。自動判定)か、Whisper の言語コード(`en`、`ja` など)。`Japanese` のような言語名や大文字も受け付けます。対応していない値は `auto` に戻ります。
  - 自動判定は発話の区間ごとに行うため、「はい」のような短い発話が別の言語と判定されることがあります。会議の言語が決まっているなら、言語を指定するのがおすすめです。
  - `dictionary.path`: 単語の辞書のファイル(既定は Tsuzuri の辞書)。`"dictionary": {"enabled": false}` にすると辞書を使いません。

### 任意: OnCue からの起動

会議の準備を行う別アプリ **OnCue**(メニューバーアプリ)を併用している場合、専用のカスタムURL
(`meetingrecorder://prepare?title=...&counterpart=...&join=...`)経由で会議名・相手の名前・Google Meet の URL を MeetingRecorder へ渡せます。自分で入力し直す必要がありません。

- `title` は必須、`counterpart` は任意、`join` は必須で `https://meet.google.com/...` の URL である必要があります。それ以外(scheme・host が違う、未知のクエリや重複したクエリ、Meet 以外の `join` URL など)は黙って反映せず拒否し、画面にバナーで表示します。
- 録音中(または保存中)に届いたリクエストは反映しません。今録音している会議の会議名・相手の名前はそのまま保たれ、「変更しなかった」旨をバナーで知らせます。
- MeetingRecorder は OnCue が無くても単体で動作します。この連携は OnCue も使っている人向けの補助機能で、OnCue 自体はこのリポジトリには含まれません。

### 任意: 文字起こし後に AI エージェントへ渡す

既定は**なし**です。設定すると、録音後の自動文字起こしが完了した直後に、選んだ AI エージェント(**Claude Code** または **Codex**)を作業フォルダで起動し、依頼文を送ります。MeetingRecorder 自身が渡すのは Transcript の**在り処**(ファイルパス)だけで、エージェントがそのファイルを読みます。

> **この手順では、文字起こしの本文が Mac の外に出ます。** Claude Code と Codex は、読んだ内容をそれぞれの会社(Anthropic、OpenAI)のクラウドのモデルへ送ります。音声は手元に残りますが、文字起こしの本文は、あなたのアカウントとその会社の規約のもとで送られます。内容を Mac の外に出せない会議では、送り先を「なし」のままにしてください。

- 設定できるのは **送り先**(画面の表記は Target。None / Claude Code / Codex)、**開き方**(Open with。Orca / Terminal)、**作業フォルダ**(Working directory。エージェントを起動する場所)、**依頼文**(複数行。プレースホルダ `{transcript}` `{session}` `{title}` `{counterpart}` を置換。空にすると既定の文を使う)、**対象の会議名の絞り込み文字列**(空欄なら常に実行)の5つです。`{title}` と `{counterpart}` は OnCue の呼び出しなど外から入ることがあるので、依頼文の中では信用できない文字として扱ってください。
- **Orca で開く**場合: `orca terminal create` で新しい端末を作り、入力待ちになったのを確認してから依頼文を送ります。**作業フォルダをあらかじめ Orca に登録しておく必要があります**(未登録のフォルダは worktree として開けません)。
- **ターミナルで開く**場合: 作業フォルダで `claude` または `codex` を依頼文つきで対話起動します(macOS の「ターミナル」を使用)。アプリで分かるのはターミナルを開けたところまでです。作業フォルダが無い、コマンドが PATH に無いといった失敗は、ターミナルの画面に出ます。
- どちらも `claude` / `codex` はログインシェルの PATH で解決します(Homebrew などで入れた場所を PATH に通しておいてください)。
- **動作する条件**: 録音を止めた直後の**自動文字起こし**が両 Transcript の保存まで成功し、送り先が「なし」以外で、作業フォルダが設定済みで、会議名の絞り込みに一致したときだけ動作します。「今すぐ文字起こし」の一括処理(未処理をまとめて処理)では動作しません。失敗しても録音・文字起こしの結果には影響せず、画面に最後の結果(成功・失敗の理由)を短く出します。
- **これは会議の内容を読めるローカルの AI エージェントを、無人で自動起動する機能です。** 信頼できる送り先だけを選んでください。

## 動作要件

- **macOS 15.6 (Sequoia) 以降**(ScreenCaptureKit の単一ストリームでマイクとシステム音声を同時取得するため)。
- 文字起こしを使う場合: Apple Silicon(MLX の GPU 実行)と [uv](https://docs.astral.sh/uv/)。
- ビルドには Xcode 26 以降が必要です(Xcode 26.4 で確認)。署名済みのリリースビルドはありません([SETUP.ja.md](SETUP.ja.md) 参照)。

### 必要な権限

| 権限 | 用途 |
| --- | --- |
| マイク | 自分の発話の録音 |
| 画面とシステムオーディオの録音 | 会議相手の声(システム音声)の録音 |
| ファイルとフォルダ ― 書類フォルダ | 録音・Transcript は `~/Documents/MeetingRecorder` 配下。文字起こしの子プロセスもここを読み書きする |
| フルディスクアクセス(最後の手段) | 上の書類フォルダの許可だけでは足りない場合だけ。保護対象外の普通のフォルダ(デスクトップ・書類・ダウンロード・iCloud Drive などを除く場所)は本来どこでも追加の許可なしにアクセスできるので、これが必要になるのは逆に、`postprocess` の CLI/venv を iCloud Drive のような**別の保護・同期対象の場所の中**に置いていて、書類フォルダの許可では届かない場合 |

単一ストリーム構成のため、**映像を保存しなくても画面収録権限が必須**です(無いとマイクも録音できません)。権限が不足しているとアプリが録音ボタンを無効化し、システム設定への導線を表示します。

書類フォルダへのアクセスは、アプリや文字起こしの子プロセスが `~/Documents` に初めて触れたときに macOS が自動でプロンプトを出します。事前に何かを設定する必要はありません。フルディスクアクセスは、それでも文字起こしが権限エラーで失敗する場合だけ試してください。

## セットアップ

ソースからのビルドには、Xcode の署名設定・Python 側のセットアップ・モデルのダウンロードが絡みます。手順は **[SETUP.ja.md](SETUP.ja.md)** にまとめてあります([SETUP.md](SETUP.md) が英語版)。要約すると:

```sh
git clone https://github.com/GentaAmeku/MeetingRecorder.git
cd MeetingRecorder
cp MeetingRecorder/Configuration/Local.xcconfig.example MeetingRecorder/Configuration/Local.xcconfig
# Local.xcconfig を編集: 自分の DEVELOPMENT_TEAM と MEETING_RECORDER_BUNDLE_ID_PREFIX
open MeetingRecorder/MeetingRecorder.xcodeproj   # Xcode でビルド・実行

scripts/install_app.sh                            # 文字起こしを使う場合はこちら
# postprocess の uv sync も含めてビルド・インストールし、CLI の場所も自動設定します
```

配布は**ソースからのビルドのみ**です。署名済み・公証済みのリリースや Homebrew での配布はありません。

## 使い方

1. アプリを起動。
2. (任意)マイク・会議名・相手の名前を設定。
3. 会議中に **Start Recording** を押す。
4. 会議終了時に **Stop** を押す(停止後にそのまま Transcript が作られます)。
5. **Show in Finder** で録音物・Transcript を確認。

録音物は `~/Documents/MeetingRecorder/recordings/<日時>_<会議名>/` に保存されます。

```
~/Documents/MeetingRecorder/recordings/
  index.json                       # 全セッションのカタログ
  2026-06-30_1530_週次定例/
    mic.wav        # 既定では文字起こし完了後に削除(設定ONなら保持)
    system.wav     # 既定では文字起こし完了後に削除(設定ONなら保持)
    metadata.json
    transcript.md  # 自分/相手の会話ログ(文字起こし後)
    transcript.json
```

## 既知の制限

- アプリの画面はすべて英語で、実行時に切り替える言語設定や多言語化の仕組みはありません(変えるにはソースの編集が必要です)。Transcript の話者名と文字起こしの言語は、上で説明したとおり実行時に個別に設定できます。AI エージェントへ渡す依頼文の既定値も英語ですが、設定画面でどの言語にでも書き換えられます。

## モデル・依存ライブラリのライセンス

文字起こし・話者分離はダウンロードするサードパーティのモデルを使います。各モデル・主要な依存が何のライセンスで公開されているか、何を確認して分かったかは [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) にまとめています。

## さらに詳しく

- 文字起こしパイプラインの内部・CLI オプション: [postprocess/README.md](postprocess/README.md)

## ライセンス

[MIT](LICENSE)。
