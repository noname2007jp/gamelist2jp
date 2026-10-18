# gamelist2jp

Windows用GUIツール。機種別フォルダの `gamelist.xml` を読み取り、日本版ROM候補を判定して出力先へコピーします。

## ビルドとダウンロード
GitHub Actions の **Build Windows EXE** が Windows ランナー上で PyInstaller を実行し、`gamelist2jp.exe` を成果物として保存します。Actions の実行結果から Artifact をダウンロードしてください。

## 使い方
1. 起動して、機種フォルダを含む親フォルダを選びます。
2. 出力先フォルダを選びます。
3. 「スキャン・判定」を実行します。
4. 一覧のフィルターで「日本」「対象外」「要確認」を複数同時に表示できます。
5. 「『日本』をコピー」で日本判定分をまとめてコピーするか、一覧で行を選択してコピーします。
6. ゲーム名の表示・検索・出力時の `<name>` は `<zh_CN>` → `<en_US>` → `<name>` → ROMファイル名の順で採用します。判定にはこれらのタイトルに加え、ROMファイル名・パス・地域/言語フィールドも使用します。
7. 選択したゲームは LaunchBox Games Database で検索できます。

## 判定について
ROMファイル名/パスの地域表記（J/Japan、USA/Europe等）、タイトル、gamelistの地域・言語情報、hack/demo等の表記から候補判定します。これはヒューリスティック判定であり、ROMの内容やハッシュを照合する完全な検証ではありません。曖昧な候補は人が確認してください。

TheGamesDB APIキー欄は任意です。APIの応答を補助情報として表示しますが、現状ではAPI結果そのものを日本版判定の根拠にはしていません。外部APIの仕様や利用条件は変更される可能性があります。

## 出力
- 機種別サブフォルダにROM、参照画像、`gamelist.xml` を出力します。
- 元ROMや元XMLは変更しません。
- 出力先の同名ROMは上書きせずスキップします。
- コピー結果は `jproms_report.csv` に記録します。

## 初期対象機種
arcade, atari2600, atarilynx, cps1, cps2, cps3, gamegear, gb, gba, gbc, genesis, megadrive, nes, ngpc, pcengine, psp, psx, SMS, snes, wonder
