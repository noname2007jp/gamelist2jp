# gamelist2jp

Windows用GUIツール。機種別フォルダの `gamelist.xml` を読み取り、日本版ROM候補を判定して出力先へコピーします。

## ビルドとダウンロード
GitHub Actions の **Build Windows EXE** が Windows ランナー上で PyInstaller を実行し、`gamelist2jp.exe` を成果物として保存します。Actions の実行結果から Artifact をダウンロードしてください。

## 使い方
1. 起動して、機種フォルダを含む親フォルダを選びます。
2. 出力先フォルダを選びます。
3. 「スキャン・判定」を実行します。
4. 確度の高い候補は「自動採用をコピー」、曖昧なものは一覧で選択してコピーします。
5. 選択したゲームは LaunchBox Games Database で検索できます。

## 判定について
地域表記（J/Japan、USA/Europe等）、日本語タイトル、hack/bootleg等の表記から候補判定します。これは初期版のヒューリスティック判定であり、ROMの内容やハッシュを照合する完全な検証ではありません。曖昧な候補は必ず人が確認してください。

TheGamesDB APIキー欄は任意です。APIの応答を補助情報として表示しますが、API結果だけで日本版と断定しません。外部APIの仕様や利用条件は変更される可能性があります。

## 安全性
元ROMや元XMLは変更しません。出力先の同名ROMは上書きせずスキップします。コピー結果は `jproms_report.csv` に記録します。

## 初期対象機種
arcade, atari2600, atarilynx, cps1, cps2, cps3, gamegear, gb, gba, gbc, genesis, megadrive, nes, ngpc, pcengine, psp, psx, SMS, snes, wonder
