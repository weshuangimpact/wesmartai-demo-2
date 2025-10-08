# ====================================================================
# WesmartAI 證據報告 Web App (final7.7-secure, base64-hash + safeguard)
# 修改要點：
# 1. 先保存原始 image bytes，不使用 Pillow 重儲存。
# 2. 對 Base64 字串計算 SHA-256。
# 3. 若使用者未先生成圖片即按報告，給出防呆提示。
# ====================================================================

import requests, json, hashlib, uuid, datetime, random, time, os, io, base64
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
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

# --- Helper Functions ---
def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()

def sanitize_text(t, max_len=150):
    if not t:
        return ""
    t = t.replace("\r", " ").replace("\t", " ").replace("\n", " ")
    return t[:max_len] + "..." if len(t) > max_len else t

# --- PDF 報告類別 ---
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not os.path.exists("NotoSansTC.otf"):
            print("正在下載中文字型...")
            try:
                font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
                r = requests.get(font_url)
                r.raise_for_status()
                with open("NotoSansTC.otf", "wb") as f:
                    f.write(r.content)
                print("字型下載完成。")
            except Exception as e:
                print(f"字型下載失敗: {e}")
        self.add_font("NotoSansTC", "", "NotoSansTC.otf")
        self.set_auto_page_break(auto=True, margin=25)
        self.alias_nb_pages()
        self.logo_path = "LOGO.jpg" if os.path.exists("LOGO.jpg") else None

    def header(self):
        if self.logo_path:
            with self.local_context(fill_opacity=0.08, stroke_opacity=0.08):
                img_w = 120
                center_x = (self.w - img_w) / 2
                center_y = (self.h - img_w) / 2
                self.image(self.logo_path, x=center_x, y=center_y, w=img_w)
        if self.page_no() > 1:
            self.set_font("NotoSansTC", "", 9)
            self.set_text_color(128)
            self.cell(0, 10, "WesmartAI 生成式 AI 證據報告", new_x=XPos.LMARGIN, new_y=YPos.TOP, align='L')
            self.cell(0, 10, "WesmartAI Inc.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')

    def footer(self):
        self.set_y(-15)
        self.set_font("NotoSansTC", "", 8)
        self.set_text_color(128)
        self.cell(0, 10, f'第 {self.page_no()}/{{nb}} 頁', align='C')

    def chapter_title(self, title):
        self.set_font("NotoSansTC", "", 16)
        self.set_text_color(0)
        self.cell(0, 12, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        self.ln(6)

    def chapter_body(self, content):
        self.set_font("NotoSansTC", "", 10)
        self.set_text_color(50)
        self.multi_cell(0, 7, content, align='L')
        self.ln()

    def create_cover(self, meta):
        self.add_page()
        if self.logo_path:
            img_w = 60
            center_x = (self.w - img_w) / 2
            self.image(self.logo_path, x=center_x, y=25, w=img_w)
        self.set_y(100)
        self.set_font("NotoSansTC", "", 28)
        self.cell(0, 20, "WesmartAI 證據報告", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(20)
        self.set_font("NotoSansTC", "", 12)
        col_width = 45
        line_height = 10
        indent = 20
        data = [
            ("出證申請人:", meta['applicant']),
            ("申請事項:", "WesmartAI 生成式 AI 證據報告"),
            ("申請出證時間:", meta['report_time']),
            ("出證編號:", meta['report_id']),
            ("出證單位:", "WesmartAI Inc.")
        ]
        for row in data:
            self.cell(indent)
            self.cell(col_width, line_height, row[0], align='L')
            self.cell(0, line_height, row[1], new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')

    def create_disclaimer_page(self):
        self.add_page()
        self.chapter_title("声 明")
        self.chapter_body(
            "本公司 WesmartAI Inc. (以下簡稱「本公司」) 受客戶委託，就本次生成式人工智慧 (Generative AI) "
            "服務過程中的數位資料進行存證，並出具此報告。\n\n"
            "1. 本報告中所記錄的資料，均來自於使用者與本公司系統互動時所產生的真實數位紀錄。\n"
            "2. 本公司採用區塊鏈技術理念，對生成過程中的關鍵數據（包括但不限於：使用者輸入、模型參數、生成結果的雜湊值、時間戳記）進行不可變紀錄。\n"
            "3. 本報告僅對數據來源與完整性負責，不對生成內容合法性或版權提供背書。\n"
            "4. 協力廠商基於報告所為之決策與後果由其自負。\n"
            "5. 報告數位與紙本版本具同等效力，可透過 QR code 驗證真偽。\n\n"
            "特此聲明。"
        )

    def create_overview_page(self):
        self.add_page()
        self.chapter_title("技術概述")
        self.chapter_body(
            "WesmartAI 的圖像生成存證服務以「生成即存證」為核心。每一次 AI 圖像生成均自動記錄輸入指令、模型參數、時間戳記與雜湊值，確保透明、可追溯、不可竄改。"
        )

    def create_generation_details_page(self, experiment_meta, snapshots):
        self.add_page()
        self.chapter_title("一、生成任務基本資訊")
        self.set_font("NotoSansTC", "", 10)
        for key, value in experiment_meta.items():
            self.cell(0, 7, f"{key}: {value}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)

        self.chapter_title("二、各版本生成快照")
        for snapshot in snapshots:
            self.set_font("NotoSansTC", "", 10)
            self.cell(0, 7, f"版本索引: {snapshot['version_index']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.multi_cell(0, 6, f"  - 時間戳記 (UTC): {snapshot['sealed_at']}\n"
                                   f"  - 圖像雜湊 (SHA-256): {snapshot['snapshot_hash']}\n"
                                   f"  - 輸入指令 (Prompt): {snapshot['input_data']['prompt']}\n"
                                   f"  - 隨機種子 (Seed): {snapshot['input_data']['seed']}")
            self.ln(4)
            if os.path.exists(snapshot['generated_image']):
                self.image(snapshot['generated_image'], w=80, x=(self.w - 80) / 2)
            self.ln(10)

    def create_conclusion_page(self, event_hash, num_snapshots):
        self.add_page()
        self.chapter_title("三、結論")
        self.chapter_body(
            f"本次任務共封存 {num_snapshots} 個版本的生成快照。所有快照元數據已整合為最終事件雜湊值 (Final Event Hash)："
        )
        self.set_font("Courier", "B", 10)
        self.multi_cell(0, 8, event_hash, border=1, align='C')
        self.ln(10)
        qr_data = f"https://wesmart.ai/verify?hash={event_hash}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{event_hash[:10]}.png")
        qr_img.save(qr_path)
        self.image(qr_path, w=50, x=(self.w - 50) / 2)
        self.ln(5)
        self.cell(0, 8, "掃描 QR Code 驗證報告真偽", align='C')

# --- 全域會話變數 ---
trace_token = str(uuid.uuid4())
snapshots = []
version_counter = 1

@app.route('/')
def index():
    global snapshots, version_counter, trace_token
    snapshots, version_counter, trace_token = [], 1, str(uuid.uuid4())
    api_key_set = bool(API_KEY)
    return render_template('index.html', api_key_set=api_key_set)

# === 生成圖片 ===
@app.route('/generate', methods=['POST'])
def generate():
    global version_counter
    if not API_KEY:
        return jsonify({"error": "後端尚未設定 TOGETHER_API_KEY 環境變數"}), 500

    data = request.json
    prompt = data.get('prompt')
    seed_input = data.get('seed')
    width = int(data.get('width', 512))
    height = int(data.get('height', 512))

    if not prompt:
        return jsonify({"error": "Prompt 為必填項"}), 400

    seed_value = int(seed_input) if seed_input and seed_input.isdigit() else random.randint(1, 10**9)
    url = "https://api.together.xyz/v1/images/generations"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "seed": seed_value, "steps": 8, "width": width, "height": height}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        res.raise_for_status()
        res_data = res.json()
        image_url = res_data["data"][0]["url"]
        image_response = requests.get(image_url, timeout=60)
        image_response.raise_for_status()
        img_bytes = image_response.content

        # --- 直接保存原始 bytes ---
        filename = f"v{version_counter}_{int(time.time())}.png"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, "wb") as f:
            f.write(img_bytes)

        # --- Base64 編碼 + 雜湊 ---
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        snapshot_hash = sha256_bytes(img_base64.encode("utf-8"))

        sealed_block = {
            "version_index": version_counter,
            "trace_token": trace_token,
            "input_data": payload,
            "snapshot_hash": snapshot_hash,
            "sealed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "generated_image": filepath
        }

        snapshots.append(sealed_block)
        version_counter += 1
        image_preview_url = url_for('static_preview', filename=filename)
        return jsonify({"success": True, "image_url": image_preview_url, "version": version_counter - 1, "seed": seed_value})

    except Exception as e:
        return jsonify({"error": f"生成失敗: {str(e)}"}), 500

# === 生成報告 ===
@app.route('/finalize', methods=['POST'])
def finalize():
    global snapshots
    data = request.json
    applicant_name = data.get('applicant_name')

    # 防呆：未先生成圖片禁止出報告
    if not snapshots:
        return jsonify({"error": "尚未生成任何圖片。請先完成圖像生成再出具報告。"}), 400
    if not applicant_name:
        return jsonify({"error": "出證申請人名稱為必填項"}), 400

    try:
        report_time_utc = datetime.datetime.now(datetime.timezone.utc)
        report_time_str = report_time_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
        report_id = str(uuid.uuid4())

        pdf = WesmartPDFReport()
        pdf.create_cover({'applicant': applicant_name, 'report_time': report_time_str, 'report_id': report_id})
        pdf.create_disclaimer_page()
        pdf.create_overview_page()

        experiment_meta = {
            "Trace Token": trace_token,
            "出證申請人": applicant_name,
            "首次生成時間": snapshots[0]['sealed_at'],
            "最終生成時間": snapshots[-1]['sealed_at'],
            "總共版本數": len(snapshots),
            "使用模型": snapshots[0]['input_data'].get('model', 'N/A')
        }
        pdf.create_generation_details_page(experiment_meta, snapshots)

        final_event_data = json.dumps(snapshots, sort_keys=True, ensure_ascii=False).encode('utf-8')
        final_event_hash = sha256_bytes(final_event_data)
        pdf.create_conclusion_page(final_event_hash, len(snapshots))

        report_filename = f"WesmartAI_Report_{report_id}.pdf"
        report_path = os.path.join(app.config['UPLOAD_FOLDER'], report_filename)
        pdf.output(report_path)

        return jsonify({
            "success": True,
            "report_url": url_for('static_download', filename=report_filename),
            "image_urls": [url_for('static_download', filename=os.path.basename(s['generated_image'])) for s in snapshots]
        })

    except Exception as e:
        print(f"報告生成失敗: {e}")
        return jsonify({"error": f"報告生成失敗: {str(e)}"}), 500

# === 檔案預覽與下載 ===
@app.route('/static/preview/<path:filename>')
def static_preview(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/download/<path:filename>')
def static_download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
