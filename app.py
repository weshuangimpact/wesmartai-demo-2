# ====================================================================
# WesmartAI 證據報告 Web App (final7.4-image-positioning)
# ====================================================================

import requests, json, hashlib, uuid, datetime, random, time, os, io
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from PIL import Image
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import qrcode
import zipfile

# --- 讀取環境變數 ---
API_KEY = os.getenv("TOGETHER_API_KEY")

# --- Flask App 初始化 ---
app = Flask(__name__)
static_folder = 'static'
if not os.path.exists(static_folder):
    os.makedirs(static_folder)
app.config['UPLOAD_FOLDER'] = static_folder

# --- Helper Functions and PDF Class ---
def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()

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
            self.set_font("NotoSansTC", "", 12)
            self.cell(col_width, line_height, row[0], align='L')
            self.set_font("NotoSansTC", "", 11)
            self.cell(0, line_height, row[1], new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')

    def create_disclaimer_page(self):
        self.add_page()
        self.chapter_title("声 明")
        self.chapter_body(
            "本公司 WesmartAI Inc. (以下簡稱「本公司」) 受客戶委託，就本次生成式人工智慧 (Generative AI) 服務過程中的數位資料進行存證，並出具此報告。\n\n"
            "1. 本報告中所記錄的資料，均來自於使用者與本公司系統互動時所產生的真實數位紀錄。\n"
            "2. 本公司採用區塊鏈技術理念，對生成過程中的關鍵數據（包括但不限於：使用者輸入、模型參數、生成結果的雜湊值、時間戳記）進行了不可變的紀錄與固化。\n"
            "3. 本報告僅對存證的數據來源、紀錄過程及數據完整性負責。本報告不對生成內容的合法性、合規性、版權歸屬及商業用途提供任何形式的保證或背書。\n"
            "4. 任何協力廠商基於本報告所做的任何決策或行動，其後果由該協力廠商自行承擔，與本公司無關。\n"
            "5. 本報告的數位版本與紙質版本具有同等效力。報告的真實性可通過掃描報告中的 QR code 進行線上驗證。\n\n"
            "特此聲明。"
        )

    def create_overview_page(self):
        self.add_page()
        self.chapter_title("技術概述")
        self.chapter_body(
            "WesmartAI 的圖像生成存證服務，旨在為每一次 AI 生成操作提供透明、可追溯且難以篡改的技術證據。本服務的核心是「生成即存證」，確保從使用者提交指令到最終圖像產生的每一個環節都被記錄在案。\n\n"
            "我們的技術流程如下：\n"
            "1. **任務接收**: 使用者提交生成指令 (Prompt) 及相關參數。系統為此次會話分配一個唯一的追蹤權杖 (Trace Token)。\n"
            "2. **迭代生成**: 使用者在同一個追蹤權杖下可進行多次圖像生成。每一次生成，系統都會記錄完整的輸入參數（如 Prompt, Seed, 模型名稱等）及精確的 UTC 時間戳記。\n"
            "3. **數據固化**: 系統對每一次生成的圖像原始二進位數據計算 SHA-256 雜湊值。這個雜湊值是對該圖像內容的唯一數位指紋。\n"
            "4. **區塊封存**: 每一次的生成紀錄（包含輸入參數、時間戳記、圖像雜湊值等）被視為一個「區塊」。所有相關的生成紀錄會被串聯起來，形成一個不可變的證據鏈。\n"
            "5. **報告產出**: 當使用者結束任務時，系統會將整個證據鏈上的所有資訊，以及最終所有「區塊」的整合性雜湊值，一同寫入本份 PDF 報告中，以供查驗。"
        )
    
    # ====================================================================
    # 【主要修改區域】
    # ====================================================================
    def create_generation_details_page(self, experiment_meta, snapshots):
        self.add_page()
        self.chapter_title("一、生成任務基本資訊")
        self.set_font("NotoSansTC", "", 10)
        line_height = 8
        for key, value in experiment_meta.items():
            self.set_font("NotoSansTC", "", 10)
            self.cell(40, line_height, f"  {key}:", align='L')
            self.set_font("NotoSansTC", "", 9)
            self.set_text_color(80)
            self.multi_cell(0, line_height, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)
        
        self.chapter_title("二、各版本生成快照")
        for snapshot in snapshots:
            self.set_font("NotoSansTC", "", 12)
            self.cell(0, 10, f"版本索引: {snapshot['version_index']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
            self.ln(2)
            
            details = [
                ("時間戳記 (UTC)", snapshot['sealed_at']),
                ("圖像雜湊 (SHA-256)", snapshot['snapshot_hash']),
                ("輸入指令 (Prompt)", snapshot['input_data']['prompt']),
                ("隨機種子 (Seed)", str(snapshot['input_data']['seed']))
            ]

            # 先渲染所有文字
            for key, value in details:
                self.set_font("NotoSansTC", "", 10)
                self.cell(45, 7, f"  - {key}:", align='L')
                self.set_font("NotoSansTC", "", 9)
                self.set_text_color(80)
                self.multi_cell(0, 7, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            self.ln(5) # 在文字和圖片之間增加一些間距

            # 渲染圖片
            if os.path.exists(snapshot['generated_image']):
                img_w = 80
                img_h = 80 # 假設圖片為方形，可根據實際情況調整
                
                # 檢查頁面剩餘空間，如果不足則新增一頁
                if self.get_y() + img_h > self.h - self.b_margin:
                    self.add_page()
                    self.chapter_title("二、各版本生成快照 (續)") # 換頁後增加標題

                self.image(snapshot['generated_image'], w=img_w, x=XPos.LMARGIN)
            
            self.ln(15) # 在每個版本之間增加更多間距

    def create_conclusion_page(self, event_hash, num_snapshots):
        self.add_page()
        self.chapter_title("三、結論")
        body = (f"本次出證任務包含 {num_snapshots} 個版本的生成快照。所有快照的元數據已被整合並計算出最終的「事件雜湊值」。\n\n"
                "此雜湊值是對整個生成歷史的唯一數位簽章，可用於驗證本報告所含數據的完整性與真實性。")
        self.chapter_body(body)
        self.ln(10)
        self.set_font("NotoSansTC", "", 12)
        self.cell(0, 10, "最終事件雜湊值 (Final Event Hash):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Courier", "B", 11)
        self.set_text_color(0)
        self.multi_cell(0, 8, event_hash, border=1, align='C', padding=5)
        qr_data = f"https://wesmart.ai/verify?hash={event_hash}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{event_hash[:10]}.png")
        img.save(qr_path)
        self.ln(10)
        self.set_font("NotoSansTC", "", 10)
        self.cell(0, 10, "使用 WesmartAI 驗證服務掃描此 QR Code 以核對報告真偽。", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.image(qr_path, w=50, x=(self.w-50)/2)

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

@app.route('/generate', methods=['POST'])
def generate():
    global version_counter
    if not API_KEY:
        return jsonify({"error": "後端尚未設定 TOGETHER_API_KEY 環境變數"}), 500
    data = request.json
    prompt, seed_input = data.get('prompt'), data.get('seed')
    width, height = int(data.get('width', 512)), int(data.get('height', 512))
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
    global snapshots
    data = request.json
    applicant_name = data.get('applicant_name')
    if not applicant_name:
        return jsonify({"error": "出證申請人名稱為必填項"}), 400
    if not snapshots:
        return jsonify({"error": "沒有可供證明的生成圖像"}), 400
    try:
        report_time_utc = datetime.datetime.now(datetime.timezone.utc)
        report_time_str = report_time_utc.strftime('%Y-%m-%d %H:%M:%S %Z')
        report_id = str(uuid.uuid4())
        pdf = WesmartPDFReport()
        cover_meta = {'applicant': applicant_name, 'report_time': report_time_str, 'report_id': report_id}
        pdf.create_cover(cover_meta)
        pdf.create_disclaimer_page()
        pdf.create_overview_page()
        first_snapshot = snapshots[0]
        experiment_meta = {
            "Trace Token": trace_token, "出證申請人": applicant_name, "首次生成時間": first_snapshot['sealed_at'],
            "最終生成時間": snapshots[-1]['sealed_at'], "總共版本數": len(snapshots), "使用模型": first_snapshot['input_data'].get('model', 'N/A')
        }
        pdf.create_generation_details_page(experiment_meta, snapshots)
        final_event_data = json.dumps(snapshots, sort_keys=True, ensure_ascii=False).encode('utf-8')
        final_event_hash = sha256_bytes(final_event_data)
        pdf.create_conclusion_page(final_event_hash, len(snapshots))
        pdf_bytes = pdf.output()
        zip_filename = f"WesmartAI_Package_{report_id}.zip"
        zip_filepath = os.path.join(app.config['UPLOAD_FOLDER'], zip_filename)
        with zipfile.ZipFile(zip_filepath, 'w') as zipf:
            zipf.writestr("WesmartAI_證據報告.pdf", pdf_bytes)
            for snapshot in snapshots:
                image_path = snapshot['generated_image']
                if os.path.exists(image_path):
                    zipf.write(image_path, arcname=os.path.basename(image_path))
        return jsonify({
            "success": True,
            "report_url": url_for('static', filename=zip_filename)
        })
    except Exception as e:
        print(f"Error during package generation: {e}")
        return jsonify({"error": f"報告與圖像打包失敗: {str(e)}"}), 500

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
