import csv
import re
import shutil
import threading
import urllib.parse
import urllib.request
import json
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET
from pathlib import Path

APP = "gamelist2jp"
PLATFORMS = {"arcade", "atari2600", "atarilynx", "cps1", "cps2", "cps3", "gamegear", "gb", "gba", "gbc", "genesis", "megadrive", "nes", "ngpc", "pcengine", "psp", "psx", "sms", "snes", "wonder"}
JP_MARKERS = re.compile(r"(\(J\)|\[J\]|\(Japan\)|\[Japan\]|\(Japanese\)|\[Japanese\]|Japanese Version|Japan(?:ese)?[-_ ]?Only|日本版|日本語版|国内版|日本国内|日本向け|\(日\))", re.I)
NONJP_MARKERS = re.compile(r"(\(U\)|\[U\]|\(USA\)|\[USA\]|\(E\)|\[E\]|\(Europe\)|\[Europe\]|\(World\)|\[World\]|\(Korea\)|\[Korea\]|\(Asia\)|\[Asia\]|\(Brazil\)|\[Brazil\]|\(Australia\)|\[Australia\]|\(Germany\)|\[Germany\]|\(France\)|\[France\]|\(Spain\)|\[Spain\]|\(Italy\)|\[Italy\]|\(China\)|\[China\]|\(Taiwan\)|\[Taiwan\])", re.I)
HACK_MARKERS = re.compile(r"\b(hack|bootleg|unl|pirate|translation|translated|prototype|beta|demo|sample)\b", re.I)
JP_TEXT = re.compile(r"[ぁ-んァ-ヶ一-龠]")
REGION_FIELDS = ("region", "lang", "language", "country")

def text_of(node, tag):
    e = node.find(tag)
    return (e.text or "").strip() if e is not None else ""

def localized_title(game, rom):
    # The source <name> can be malformed or contain emulator-specific labels.
    # Prefer the explicit localized fields, retaining all fields for identification.
    return text_of(game, "zh_CN") or text_of(game, "en_US") or text_of(game, "name") or rom.stem

def classify(game, rom_name, rom_path):
    fields = {
        "name": text_of(game, "name"),
        "zh_CN": text_of(game, "zh_CN"),
        "en_US": text_of(game, "en_US"),
        "filename": rom_name,
        "path": str(rom_path),
        "region": " ".join(text_of(game, t) for t in REGION_FIELDS),
    }
    hay = " ".join(fields.values())
    reasons = []
    score = 0
    # Region labels in the ROM filename/path carry more weight than display titles.
    if JP_MARKERS.search(fields["filename"]) or JP_MARKERS.search(fields["path"]):
        score += 10
        reasons.append("ROMファイル名/パスに日本版表記")
    elif JP_MARKERS.search(hay):
        score += 8
        reasons.append("日本版を示す地域表記")
    if NONJP_MARKERS.search(fields["filename"]) or NONJP_MARKERS.search(fields["path"]):
        score -= 12
        reasons.append("ROMファイル名/パスに海外版表記")
    elif NONJP_MARKERS.search(hay):
        score -= 10
        reasons.append("海外版を示す地域表記")
    if HACK_MARKERS.search(hay):
        score -= 6
        reasons.append("hack/demo等の表記")
    if any(JP_TEXT.search(fields[k]) for k in ("name", "zh_CN", "en_US")):
        score += 3
        reasons.append("タイトルに日本語文字")
    region = fields["region"].lower()
    if any(x in region for x in ("japan", "japanese", "日本", " jp ")):
        score += 5
        reasons.append("gamelistの地域/言語情報")
    if any(x in region for x in ("usa", "europe", "world", "korea", "china", "taiwan", "english", "french", "german")):
        score -= 5
        reasons.append("gamelistの地域/言語情報が日本以外")
    if score >= 7:
        return "日本", " / ".join(reasons)
    if score <= -6:
        return "対象外", " / ".join(reasons)
    return "要確認", " / ".join(reasons) if reasons else "地域を特定できる情報が不足"

def thegamesdb_lookup(name, api_key):
    if not api_key.strip():
        return None
    url = "https://api.thegamesdb.net/v1/Games/ByGameName?" + urllib.parse.urlencode({
        "apikey": api_key.strip(), "name": name, "fields": "overview,players,publishers,genres,platform"
    })
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gamelist2jp/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        games = data.get("data", {}).get("games", {})
        if games:
            g = next(iter(games.values()))
            return (g.get("game_title") or g.get("name") or "", g.get("release_date") or "", g.get("platform") or "")
    except Exception:
        return None
    return None

def resolve_xml_path(base, value):
    value = (value or "").strip()
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        return p
    return (base / value.removeprefix("./").replace("/", "\\" )).resolve()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("gamelist2jp - 日本版ROM抽出")
        self.geometry("1260x760")
        self.minsize(980, 600)
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.api_key = tk.StringVar()
        self.status = tk.StringVar(value="親フォルダを選択してください。")
        self.rows = []
        self.filter_vars = {
            "日本": tk.BooleanVar(value=True),
            "対象外": tk.BooleanVar(value=True),
            "要確認": tk.BooleanVar(value=True),
        }
        self._ui()

    def _ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="ROMフォルダ（各機種フォルダを含む親フォルダ）").grid(row=0, column=0, sticky="w")
        ttk.Entry(root, textvariable=self.source).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(root, text="参照...", command=self.pick_source).grid(row=1, column=1)
        ttk.Label(root, text="出力先（jproms）").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(root, textvariable=self.output).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(root, text="参照...", command=self.pick_output).grid(row=3, column=1)
        ttk.Label(root, text="TheGamesDB APIキー（任意・照合情報用）").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(root, textvariable=self.api_key, show="•").grid(row=5, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(root, text="APIキー取得ページ", command=lambda: webbrowser.open("https://thegamesdb.net/")).grid(row=5, column=1)
        bar = ttk.Frame(root)
        bar.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        ttk.Button(bar, text="スキャン・判定", command=self.start_scan).pack(side="left")
        ttk.Button(bar, text="「日本」をコピー", command=self.copy_auto).pack(side="left", padx=8)
        ttk.Button(bar, text="選択行を日本としてコピー", command=self.copy_selected).pack(side="left")
        ttk.Button(bar, text="選択行をLaunchBoxで検索", command=self.search_selected).pack(side="left", padx=8)
        filters = ttk.LabelFrame(root, text="表示フィルター（複数選択可）", padding=(8, 4))
        filters.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        for label, var in self.filter_vars.items():
            ttk.Checkbutton(filters, text=label, variable=var, command=self.apply_filters).pack(side="left", padx=(0, 18))
        cols = ("platform", "title", "zh_CN", "en_US", "rom", "status", "reason", "db")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", selectmode="extended")
        headings = {"platform": "機種", "title": "表示タイトル（zh_CN→en_US）", "zh_CN": "<zh_CN>", "en_US": "<en_US>", "rom": "ROMファイル名", "status": "判定", "reason": "判定理由", "db": "DB情報"}
        widths = {"platform": 78, "title": 190, "zh_CN": 170, "en_US": 170, "rom": 220, "status": 75, "reason": 230, "db": 150}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")
        self.tree.grid(row=8, column=0, columnspan=2, sticky="nsew")
        ys = ttk.Scrollbar(root, orient="vertical", command=self.tree.yview)
        ys.grid(row=8, column=2, sticky="ns")
        self.tree.configure(yscrollcommand=ys.set)
        ttk.Label(root, textvariable=self.status).grid(row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(8, weight=1)

    def pick_source(self):
        p = filedialog.askdirectory(title="機種フォルダを含む親フォルダを選択")
        if p:
            self.source.set(p)

    def pick_output(self):
        p = filedialog.askdirectory(title="出力先フォルダを選択")
        if p:
            self.output.set(p)

    def start_scan(self):
        src_text = self.source.get().strip()
        src = Path(src_text) if src_text else None
        if src is None or not src.is_dir():
            messagebox.showerror("入力エラー", "有効な親フォルダを選択してください。")
            return
        self.rows = []
        self.tree.delete(*self.tree.get_children())
        self.status.set("スキャン中...")
        threading.Thread(target=self.scan_worker, args=(src, self.api_key.get().strip()), daemon=True).start()

    def scan_worker(self, src, api_key):
        found = []
        entries = []
        # First parse the XML files and count valid game entries so progress can show N/N.
        xml_files = []
        for xml in src.rglob("gamelist.xml"):
            platform = xml.parent.name
            if platform.lower() not in PLATFORMS:
                continue
            try:
                xml_root = ET.parse(xml).getroot()
            except Exception:
                continue
            xml_files.append((xml, platform, xml_root))
            for game in xml_root.findall("game"):
                rel = text_of(game, "path")
                rom = resolve_xml_path(xml.parent, rel)
                if rom is not None:
                    entries.append((xml, platform, game, rel, rom))

        total = len(entries)
        self.after(0, lambda total=total: self.status.set(f"スキャン準備完了：対象 {total} 件"))
        for index, (xml, platform, game, rel, rom) in enumerate(entries, start=1):
            # Update the visible status for every ROM, including while waiting on a DB request.
            self.after(0, lambda i=index, n=total, filename=rom.name:
                       self.status.set(f"スキャン中：{i}/{n} {filename}"))
            title = localized_title(game, rom)
            zh = text_of(game, "zh_CN")
            en = text_of(game, "en_US")
            state, reason = classify(game, rom.name, rom)
            dbinfo = ""
            # Only uncertain titles need an external lookup; clear Japan/non-Japan cases skip the API.
            info = thegamesdb_lookup(title, api_key) if api_key and state == "要確認" else None
            if state == "要確認" and api_key:
                dbinfo = "DB検索済み（候補なし）"
            if info:
                dbinfo = "候補: " + (info[0] or title)
                if info[1]:
                    dbinfo += " / " + info[1]
            found.append({"xml": xml, "game": game, "platform": platform, "title": title,
                          "zh_CN": zh, "en_US": en, "rom": rom, "rel": rel,
                          "image": text_of(game, "image"), "status": state, "reason": reason, "db": dbinfo})
        self.after(0, lambda: self.show_results(found))

    def show_results(self, found):
        self.rows = found
        self.apply_filters()
        counts = {s: sum(r["status"] == s for r in found) for s in self.filter_vars}
        self.status.set(f"完了：{len(found)}件 / 日本 {counts['日本']}件 / 要確認 {counts['要確認']}件 / 対象外 {counts['対象外']}件")
        if not found:
            messagebox.showinfo("結果", "対象機種の gamelist.xml が見つかりませんでした。")

    def apply_filters(self):
        self.tree.delete(*self.tree.get_children())
        visible = 0
        for i, r in enumerate(self.rows):
            if not self.filter_vars[r["status"]].get():
                continue
            self.tree.insert("", "end", iid=str(i), values=(r["platform"], r["title"], r["zh_CN"], r["en_US"], r["rom"].name, r["status"], r["reason"], r["db"]))
            visible += 1
        if hasattr(self, "status") and self.rows:
            counts = {s: sum(r["status"] == s for r in self.rows) for s in self.filter_vars}
            self.status.set(f"全{len(self.rows)}件 / 表示 {visible}件 / 日本 {counts['日本']}件 / 要確認 {counts['要確認']}件 / 対象外 {counts['対象外']}件")

    def search_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "検索したい行を選択してください。")
            return
        r = self.rows[int(sel[0])]
        query = " ".join(x for x in (r["zh_CN"], r["en_US"], r["rom"].stem, r["platform"]) if x)
        webbrowser.open("https://gamesdb.launchbox-app.com/search?searchString=" + urllib.parse.quote(query))

    def copy_auto(self):
        self.copy_rows([r for r in self.rows if r["status"] == "日本"])

    def copy_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "コピーしたい行を選択してください。")
            return
        self.copy_rows([self.rows[int(i)] for i in sel])

    def copy_rows(self, selected):
        out_text = self.output.get().strip()
        if not out_text:
            messagebox.showerror("出力先", "出力先フォルダを選択してください。")
            return
        out = Path(out_text)
        if not selected:
            messagebox.showinfo("対象なし", "コピー対象がありません。")
            return
        try:
            out.mkdir(parents=True, exist_ok=True)
            groups = {}
            report = []
            for r in selected:
                destdir = out / r["platform"]
                destdir.mkdir(parents=True, exist_ok=True)
                if not r["rom"].is_file():
                    report.append([r["platform"], r["title"], str(r["rom"]), "失敗", "ROMファイルが見つからない"])
                    continue
                target = destdir / r["rom"].name
                if target.exists():
                    report.append([r["platform"], r["title"], str(target), "スキップ", "同名ファイルが存在"])
                    continue
                shutil.copy2(r["rom"], target)
                game = ET.fromstring(ET.tostring(r["game"], encoding="utf-8"))
                path_el = game.find("path")
                if path_el is None:
                    path_el = ET.SubElement(game, "path")
                path_el.text = "./" + target.name
                # Normalize the output display name using localized title metadata.
                name_el = game.find("name")
                if name_el is None:
                    name_el = ET.SubElement(game, "name")
                name_el.text = r["title"]
                image_rel = r["image"]
                if image_rel:
                    source_img = resolve_xml_path(r["xml"].parent, image_rel)
                    if source_img and source_img.is_file():
                        imdir = destdir / "images"
                        imdir.mkdir(exist_ok=True)
                        imtarget = imdir / source_img.name
                        if not imtarget.exists():
                            shutil.copy2(source_img, imtarget)
                        im = game.find("image")
                        if im is None:
                            im = ET.SubElement(game, "image")
                        im.text = "./images/" + imtarget.name
                    else:
                        report.append([r["platform"], r["title"], str(source_img or image_rel), "警告", "画像が見つからない"])
                groups.setdefault(r["platform"], []).append(game)
                report.append([r["platform"], r["title"], str(target), "コピー", r["status"] + ": " + r["reason"]])
            for platform, games in groups.items():
                root = ET.Element("gameList")
                for game in games:
                    root.append(game)
                ET.indent(root, space="  ")
                ET.ElementTree(root).write(out / platform / "gamelist.xml", encoding="utf-8", xml_declaration=True)
            with (out / "jproms_report.csv").open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["機種", "ゲーム名", "パス", "結果", "理由"])
                writer.writerows(report)
            messagebox.showinfo("コピー完了", f"処理対象: {len(selected)}件\n出力先: {out}\n詳細: jproms_report.csv")
            self.status.set(f"コピー処理完了：{len(selected)}件")
        except Exception as e:
            messagebox.showerror("コピーエラー", str(e))

if __name__ == "__main__":
    App().mainloop()
