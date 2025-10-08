# ====================================================================
# WesmartAI 證據報告 Web App (final7.1-secure)
# 作者: Gemini
# 修正: 移除前端 API Key 輸入，改為從後端環境變數 TOGETHER_API_KEY 安全讀取
# ====================================================================

import requests, json, hashlib, uuid, datetime, random, time, os, io
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from PIL import Image
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import qrcode

# --- 讀取環境變數 ---
API_KEY = os.getenv("TOGETHER_API_KEY")

# --- Flask App 初始化 ---
app = Flask(__name__)
static_folder = 'static'
if not os.path.exists(static_folder):
    os.makedirs(static_folder)
app.config['UPLOAD_FOLDER'] = static_folder

# ... (WesmartPDFReport 類別和公用函式與之前相同) ...
#<editor-fold desc="Helper Functions and PDF Class">
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def sanitize_text(t, max_len=150):
    if not t: return ""
    t = t.replace("\r", " ").replace("\t", " ").replace("\n", " ")
    return t[:max_len] + "..." if len(t) > max_len else t
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not os.path.exists("NotoSansTC.otf"):
            print("正在下載中文字型...")
            font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
            r = requests.get(font_url)
            with open("NotoSansTC.otf", "wb") as f: f.write(r.content)
        self.add_font("NotoSansTC", "", "NotoSansTC.otf")
        self.set_auto_page_break(auto=True, margin=25)
        self.alias_nb_pages()
        self.logo_path = "LOGO.jpg" if os.path.exists("LOGO.jpg") else None
    def header(self):
        if self.logo_path:
            with self.local_context(fill_opacity=0.08, stroke_opacity=0.08):
                img_w = 120; center_x = (self.w - img_w) / 2; center_y = (self.h - img_w) / 2
                self.image(self.logo_path, x=center_x, y=center_y, w=img_w)
        if self.page_no() > 1:
            self.set_font("NotoSansTC", "", 9); self.set_text_color(128)
            self.cell(0, 10, "WesmartAI 生成式 AI 證據報告", new_x=XPos.LMARGIN, new_y=YPos.TOP, align='L')
            self.cell(0, 10, "WesmartAI Inc.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    def footer(self):
        self.set_y(-15); self.set_font("NotoSansTC", "", 8); self.set_text_color(128)
        self.cell(0, 10, f'第 {self.page_no()}/{{nb}} 頁', align='C')
    def chapter_title(self, title):
        self.set_font("NotoSansTC", "", 16); self.set_text_color(0)
        self.cell(0, 12, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L'); self.ln(6)
    def chapter_body(self, content):
        self.set_font("NotoSansTC", "", 10); self.set_text_color(50)
        self.multi_cell(0, 7, content, align='L'); self.ln()
    def create_cover(self, meta):
        self.add_page()
        if self.logo_path:
            img_w = 60; center_x = (self.w - img_w) / 2
            self.image(self.logo_path, x=center_x, y=25, w=img_w)
        self.set_y(100); self.set_font("NotoSansTC", "", 28)
        self.cell(0, 20, "WesmartAI 證據報告", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); self.ln(20)
        self.set_font("NotoSansTC", "", 12)
        col_width = 45; line_height = 10; indent = 20
        data = [("出证申请人:", meta['applicant']), ("申请事项:", "WesmartAI 生成式 AI 證據報告"), ("申请出证时间:", meta['report_time']), ("出证编号:", meta['report_id']), ("出证单位:", "WesmartAI Inc.")]
        for row in data:
            self.cell(indent); self.set_font("NotoSansTC", "", 12); self.cell(col_width, line_height, row[0], align='L')
            self.set_font("NotoSansTC", "", 11); self.cell(0, line_height, row[1], new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    def create_disclaimer_page(self):
        self.add_page(); self.chapter_title("声 明")
        self.chapter_body("本公司 WesmartAI Inc. ... (內容同 final6.1)")
    def create_overview_page(self):
        self.add_page(); self.chapter_title("技術概述")
        self.chapter_body("WesmartAI 的圖像生成存證服務 ... (內容同 final6.1)")
    def create_generation_details_page(self, experiment_meta, snapshots):
        self.add_page(); self.chapter_title("一、生成任務基本資訊")
        # ... (內容同 final6.1)
    def create_conclusion_page(self, event_hash, num_snapshots):
        self.add_page(); self.chapter_title("三、結論")
        # ... (內容同 final6.1)
#</editor-fold>

# --- 全域會話變數 ---
trace_token = str(uuid.uuid4())
snapshots = []
version_counter = 1

@app.route('/')
def index():
    global snapshots, version_counter, trace_token
    snapshots, version_counter, trace_token = [], 1, str(uuid.uuid4())
    # 檢查 API Key 是否已在後端設定
    api_key_set = bool(API_KEY)
    return render_template('index.html', api_key_set=api_key_set)

@app.route('/generate', methods=['POST'])
def generate():
    global version_counter
    # **重大修改：不再從前端讀取 API Key**
    if not API_KEY:
        return jsonify({"error": "後端尚未設定 TOGETHER_API_KEY 環境變數"}), 500
        
    data = request.json
    prompt, seed_input = data.get('prompt'), data.get('seed')
    width, height = int(data.get('width', 512)), int(data.get('height', 512))
    
    if not prompt: return jsonify({"error": "Prompt 為必填項"}), 400
    
    seed_value = int(seed_input) if seed_input else random.randint(1, 10**9)
    url = "https://api.together.xyz/v1/images/generations"
    headers = {"Authorization": f"Bearer {API_KEY}"} # **使用從環境變數讀取的 Key**
    payload = {"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "seed": seed_value, "steps": 8, "width": width, "height": height}
    
    try:
        res = requests.post(url, headers=headers, json=payload)
        res.raise_for_status()
        res_data = res.json()
        image_url = res_data["data"][0]["url"]
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        img_bytes = image_response.content
        filename = f"v{version_counter}_{int(time.time())}.png"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        Image.open(io.BytesIO(img_bytes)).save(filepath)
        sealed_block = {"version_index": version_counter, "trace_token": trace_token, "input_data": payload, "snapshot_hash": sha256_bytes(img_bytes), "sealed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "generated_image": filepath}
        snapshots.append(sealed_block)
        version_counter += 1
        return jsonify({"success": True, "image_url": url_for('static', filename=filename), "version": version_counter - 1, "seed": seed_value})
    except Exception as e:
        return jsonify({"error": f"生成失敗: {str(e)}"}), 500

@app.route('/finalize', methods=['POST'])
def finalize():
    # ... (此函數與之前版本相同) ...
    pass

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)