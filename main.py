import os, re, csv, shutil, threading, urllib.parse, urllib.request, json, webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET
from pathlib import Path

APP = "gamelist2jp"
PLATFORMS = {"arcade","atari2600","atarilynx","cps1","cps2","cps3","gamegear","gb","gba","gbc","genesis","megadrive","nes","ngpc","pcengine","psp","psx","sms","snes","wonder"}
JP_MARKERS = re.compile(r"(\(J\)|\(Japan\)|\[Japan\]|Japanese Version|\(日本\)|日本版|国内版|\(日\))", re.I)
NONJP_MARKERS = re.compile(r"(\(U\)|\(USA\)|\(E\)|\(Europe\)|\(World\)|\[USA\]|\[Europe\])", re.I)
HACK_MARKERS = re.compile(r"(hack|bootleg|unl|pirate|translation|translated|prototype|beta)", re.I)

def text_of(node, tag):
    e = node.find(tag)
    return (e.text or "").strip() if e is not None else ""

def classify(name, path, platform, db_key=""):
    hay = name + " " + path
    reasons = []
    score = 0
    if JP_MARKERS.search(hay):
        score += 8; reasons.append("日本版を示す地域表記")
    if NONJP_MARKERS.search(hay):
        score -= 10; reasons.append("海外版を示す地域表記")
    if HACK_MARKERS.search(hay):
        score -= 6; reasons.append("hack/bootleg等の表記")
    if re.search(r"[ぁ-んァ-ヶ一-龠]", name):
        score += 5; reasons.append("日本語タイトル")
    if score >= 7:
        return "自動採用", " / ".join(reasons)
    if score <= -6:
        return "対象外", " / ".join(reasons)
    return "要確認", " / ".join(reasons) if reasons else "地域を特定できる情報が不足"

def thegamesdb_lookup(name, api_key):
    if not api_key.strip():
        return None
    # TheGamesDB API key is optional; failures never stop local scanning.
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

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("gamelist2jp - 日本版ROM抽出")
        self.geometry("1020x680")
        self.minsize(860, 560)
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.api_key = tk.StringVar()
        self.status = tk.StringVar(value="親フォルダを選択してください。")
        self.rows = []
        self._ui()

    def _ui(self):
        root = ttk.Frame(self, padding=12); root.pack(fill="both", expand=True)
        ttk.Label(root, text="ROMフォルダ（各機種フォルダを含む親フォルダ）").grid(row=0,column=0,sticky="w")
        ttk.Entry(root,textvariable=self.source).grid(row=1,column=0,sticky="ew",padx=(0,8))
        ttk.Button(root,text="参照...",command=self.pick_source).grid(row=1,column=1)
        ttk.Label(root,text="出力先（jproms）").grid(row=2,column=0,sticky="w",pady=(10,0))
        ttk.Entry(root,textvariable=self.output).grid(row=3,column=0,sticky="ew",padx=(0,8))
        ttk.Button(root,text="参照...",command=self.pick_output).grid(row=3,column=1)
        ttk.Label(root,text="TheGamesDB APIキー（任意・設定時に照合情報を取得）").grid(row=4,column=0,sticky="w",pady=(10,0))
        ttk.Entry(root,textvariable=self.api_key,show="•").grid(row=5,column=0,sticky="ew",padx=(0,8))
        ttk.Button(root,text="APIキー取得ページ",command=lambda:webbrowser.open("https://thegamesdb.net/")).grid(row=5,column=1)
        bar=ttk.Frame(root); bar.grid(row=6,column=0,columnspan=2,sticky="ew",pady=12)
        ttk.Button(bar,text="スキャン・判定",command=self.start_scan).pack(side="left")
        ttk.Button(bar,text="自動採用をコピー",command=self.copy_auto).pack(side="left",padx=8)
        ttk.Button(bar,text="選択行を日本版としてコピー",command=self.copy_selected).pack(side="left")
        ttk.Button(bar,text="選択行をLaunchBoxで検索",command=self.search_selected).pack(side="left",padx=8)
        cols=("platform","name","rom","status","reason","db")
        self.tree=ttk.Treeview(root,columns=cols,show="headings",selectmode="extended")
        headings={"platform":"機種","name":"ゲーム名","rom":"ROMファイル","status":"判定","reason":"判定理由","db":"DB情報"}
        widths={"platform":85,"name":200,"rom":210,"status":85,"reason":230,"db":150}
        for c in cols:
            self.tree.heading(c,text=headings[c]); self.tree.column(c,width=widths[c],anchor="w")
        self.tree.grid(row=7,column=0,columnspan=2,sticky="nsew")
        ys=ttk.Scrollbar(root,orient="vertical",command=self.tree.yview); ys.grid(row=7,column=2,sticky="ns")
        self.tree.configure(yscrollcommand=ys.set)
        ttk.Label(root,textvariable=self.status).grid(row=8,column=0,columnspan=2,sticky="w",pady=(8,0))
        root.columnconfigure(0,weight=1); root.rowconfigure(7,weight=1)

    def pick_source(self):
        p=filedialog.askdirectory(title="機種フォルダを含む親フォルダを選択")
        if p: self.source.set(p)
    def pick_output(self):
        p=filedialog.askdirectory(title="出力先フォルダを選択")
        if p: self.output.set(p)

    def start_scan(self):
        src=Path(self.source.get())
        if not src.is_dir():
            messagebox.showerror("入力エラー","有効な親フォルダを選択してください。"); return
        self.rows=[]; self.tree.delete(*self.tree.get_children())
        self.status.set("スキャン中...")
        threading.Thread(target=self.scan_worker,args=(src,),daemon=True).start()

    def scan_worker(self, src):
        found=[]
        for xml in src.rglob("gamelist.xml"):
            platform=xml.parent.name
            if platform.lower() not in PLATFORMS: continue
            try: root=ET.parse(xml).getroot()
            except Exception: continue
            for game in root.findall("game"):
                rel=text_of(game,"path")
                if not rel: continue
                rom=(xml.parent / rel.replace("./","",1)).resolve()
                name=text_of(game,"name") or rom.stem
                state,reason=classify(name,rom.name,platform)
                dbinfo=""
                # External DB lookup is only performed when a key is configured.
                info=thegamesdb_lookup(name,self.api_key.get()) if self.api_key.get().strip() else None
                if info:
                    dbinfo="照合候補: "+(info[0] or name)
                    if info[1]: dbinfo += " / "+info[1]
                found.append({"xml":xml,"game":game,"platform":platform,"name":name,"rom":rom,"rel":rel,
                              "image":text_of(game,"image"),"status":state,"reason":reason,"db":dbinfo})
        self.after(0,lambda:self.show_results(found))

    def show_results(self, found):
        self.rows=found
        for i,r in enumerate(found):
            self.tree.insert("","end",iid=str(i),values=(r["platform"],r["name"],r["rom"].name,r["status"],r["reason"],r["db"]))
        auto=sum(r["status"]=="自動採用" for r in found)
        review=sum(r["status"]=="要確認" for r in found)
        self.status.set(f"完了：{len(found)}件 / 自動採用 {auto}件 / 要確認 {review}件 / 対象外 {len(found)-auto-review}件")
        if not found: messagebox.showinfo("結果","対象機種の gamelist.xml が見つかりませんでした。")

    def search_selected(self):
        sel=self.tree.selection()
        if not sel: return
        r=self.rows[int(sel[0])]
        q=urllib.parse.quote(r["name"]+" "+r["platform"])
        webbrowser.open("https://gamesdb.launchbox-app.com/search?searchString="+q)

    def copy_auto(self):
        self.copy_rows([r for r in self.rows if r["status"]=="自動採用"])

    def copy_selected(self):
        sel=self.tree.selection()
        if not sel:
            messagebox.showinfo("選択なし","コピーしたい行を選択してください。"); return
        self.copy_rows([self.rows[int(i)] for i in sel])

    def copy_rows(self, selected):
        out=Path(self.output.get())
        if not str(out):
            messagebox.showerror("出力先","出力先フォルダを選択してください。"); return
        if not selected:
            messagebox.showinfo("対象なし","コピー対象がありません。"); return
        try:
            out.mkdir(parents=True,exist_ok=True)
            # Group source XML entries by platform; write a valid output gamelist for each.
            groups={}
            report=[]
            for r in selected:
                destdir=out/r["platform"]
                destdir.mkdir(parents=True,exist_ok=True)
                if not r["rom"].is_file():
                    report.append([r["platform"],r["name"],str(r["rom"]),"失敗","ROMファイルが見つからない"]); continue
                target=destdir/r["rom"].name
                if target.exists():
                    report.append([r["platform"],r["name"],str(target),"スキップ","同名ファイルが存在"]); continue
                shutil.copy2(r["rom"],target)
                game=ET.fromstring(ET.tostring(r["game"],encoding="unicode"))
                path_el=game.find("path")
                if path_el is None: path_el=ET.SubElement(game,"path")
                path_el.text="./"+target.name
                image_rel=r["image"]
                if image_rel:
                    source_img=(r["xml"].parent / image_rel.replace("./","",1)).resolve()
                    if source_img.is_file():
                        imdir=destdir/"images"; imdir.mkdir(exist_ok=True)
                        imtarget=imdir/source_img.name
                        if not imtarget.exists(): shutil.copy2(source_img,imtarget)
                        im=game.find("image")
                        if im is None: im=ET.SubElement(game,"image")
                        im.text="./images/"+imtarget.name
                    else:
                        report.append([r["platform"],r["name"],str(source_img),"警告","画像が見つからない"])
                groups.setdefault(r["platform"],[]).append(game)
                report.append([r["platform"],r["name"],str(target),"コピー","日本版候補"])
            for platform,games in groups.items():
                root=ET.Element("gameList")
                for game in games: root.append(game)
                ET.indent(root,space="  ")
                ET.ElementTree(root).write(out/platform/"gamelist.xml",encoding="utf-8",xml_declaration=True)
            with (out/"jproms_report.csv").open("w",newline="",encoding="utf-8-sig") as f:
                w=csv.writer(f); w.writerow(["機種","ゲーム名","パス","結果","理由"]); w.writerows(report)
            messagebox.showinfo("コピー完了",f"処理対象: {len(selected)}件\n出力先: {out}\n詳細: jproms_report.csv")
            self.status.set(f"コピー処理完了：{len(selected)}件")
        except Exception as e:
            messagebox.showerror("コピーエラー",str(e))

if __name__ == "__main__":
    App().mainloop()
