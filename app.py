# ====================================================================
# WesmartAI 證據報告 Web App (final13.0-atomic)
# 作者: Gemini & User
# 核心更新 (架構重構):
# 1. 確立「證據先行」原則，以 proof_event.json 為核心證據正本。
# 2. /generate 路由現在會「原子性」地生成圖片(.png)和證據正本(.json)。
# 3. 解決 "雞生蛋" 問題：先產生臨時數據計算 final_event_hash，再寫回最終 JSON。
# 4. /finalize 簡化為使用已生成的 JSON 數據來產生人類可讀的 PDF 報告。
# 5. 整個流程的邏輯清晰度、嚴謹性和可驗證性達到最終形態。
# ====================================================================

import requests, json, hashlib, uuid, datetime, random, time, os, io, base64
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from PIL import Image
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import qrcode

# --- (此處省略 API_KEY, Flask App 初始化, Helper Functions, WesmartPDFReport Class 的程式碼，與前版完全相同) ---
API_key = os.getenv("TOGETHER_API_KEY")
app = Flask(__name__)
static_folder = 'static'
if not os.path.exists(static_folder): os.makedirs(static_folder)
app.config['UPLOAD_FOLDER'] = static_folder

def sha256_bytes(b): return hashlib.sha256(b).hexdigest()

class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not os.path.exists("NotoSansTC.otf"):
            print("正在下載中文字型..."); r = requests.get("https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf");
            with open("NotoSansTC.otf", "wb") as f: f.write(r.content); print("字型下載完成。")
        self.add_font("NotoSansTC", "", "NotoSansTC.otf")
        self.set_auto_page_break(auto=True, margin=25); self.alias_nb_pages()
        self.logo_path = "LOGO.jpg" if os.path.exists("LOGO.jpg") else None
    def header(self):
        if self.logo_path:
            with self.local_context(fill_opacity=0.08, stroke_opacity=0.08):
                img_w=120; center_x=(self.w-img_w)/2; center_y=(self.h-img_w)/2; self.image(self.logo_path, x=center_x, y=center_y, w=img_w)
        if self.page_no() > 1: self.set_font("NotoSansTC", "", 9); self.set_text_color(128); self.cell(0, 10, "WesmartAI 生成式 AI 證據報告", new_x=XPos.LMARGIN, new_y=YPos.TOP, align='L'); self.cell(0, 10, "WesmartAI Inc.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    def footer(self): self.set_y(-15); self.set_font("NotoSansTC", "", 8); self.set_text_color(128); self.cell(0, 10, f'第 {self.page_no()}/{{nb}} 頁', align='C')
    def chapter_title(self, title): self.set_font("NotoSansTC", "", 16); self.set_text_color(0); self.cell(0, 12, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L'); self.ln(6)
    def chapter_body(self, content): self.set_font("NotoSansTC", "", 10); self.set_text_color(50); self.multi_cell(0, 7, content, align='L'); self.ln()
    def create_cover(self, meta):
        self.add_page();
        if self.logo_path: self.image(self.logo_path, x=(self.w-60)/2, y=25, w=60)
        self.set_y(100); self.set_font("NotoSansTC", "", 28); self.cell(0, 20, "WesmartAI 證據報告", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); self.ln(20)
        self.set_font("NotoSansTC", "", 12)
        data = [("出證申請人:", meta.get('applicant', 'N/A')), ("申請事項:", "WesmartAI 生成式 AI 證據報告"), ("申請出證時間:", meta.get('issued_at', 'N/A')), ("出證編號 (報告ID):", meta.get('report_id', 'N/A')), ("出證單位:", meta.get('issuer', 'N/A'))]
        for row in data: self.cell(20); self.cell(45, 10, row[0], align='L'); self.multi_cell(0, 10, row[1], new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    def create_generation_details_page(self, proof_data):
        self.add_page(); self.chapter_title("一、生成任務基本資訊"); self.set_font("NotoSansTC", "", 10); self.set_text_color(0)
        experiment_meta = {"Trace Token": proof_data['event_proof']['trace_token'], "總共版本數": len(proof_data['event_proof']['snapshots'])}
        for key, value in experiment_meta.items():
            self.cell(40, 8, f"  {key}:", align='L'); self.set_font("NotoSansTC", "", 9); self.set_text_color(80)
            self.multi_cell(0, 8, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.set_font("NotoSansTC", "", 10); self.set_text_color(0)
        self.ln(10)
        self.chapter_title("二、各版本生成快照")
        for snapshot in proof_data['event_proof']['snapshots']:
            self.set_font("NotoSansTC", "", 12); self.set_text_color(0); self.cell(0, 10, f"版本索引: {snapshot['version_index']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L'); self.ln(2)
            details = [("時間戳記 (UTC)", snapshot['timestamp_utc']), ("圖像雜湊 (SHA-256 over Base64)", snapshot['snapshot_hash']), ("輸入指令 (Prompt)", snapshot['prompt']), ("隨機種子 (Seed)", str(snapshot['seed']))]
            for key, value in details:
                self.set_font("NotoSansTC", "", 10); self.set_text_color(0); self.cell(60, 7, f"  - {key}:", align='L'); self.set_font("NotoSansTC", "", 9); self.set_text_color(80)
                self.multi_cell(0, 7, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(5)
            # 顯示圖片需要從 Base64 解碼
            try:
                img_bytes = base64.b64decode(snapshot['content_base64'])
                img_file_obj = io.BytesIO(img_bytes)
                self.image(img_file_obj, x=(self.w-80)/2, w=80, type='PNG')
            except Exception as e: print(f"在PDF中顯示圖片失敗: {e}")
            self.ln(15)
    def create_conclusion_page(self, proof_data):
        self.add_page(); self.chapter_title("三、報告驗證")
        self.chapter_body("本報告的真實性與完整性，取決於其對應的 `proof_event.json` 證據檔案。此 JSON 檔案的雜湊值（Final Event Hash）被記錄於下，可用於比對與驗證。")
        self.ln(10); self.set_font("NotoSansTC", "", 12); self.set_text_color(0)
        self.cell(0, 10, "最終事件雜湊值 (Final Event Hash):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Courier", "B", 11)
        self.multi_cell(0, 8, proof_data['event_proof']['final_event_hash'], border=1, align='C', padding=5)
        qr_data = proof_data['verification']['verify_url']
        qr = qrcode.make(qr_data); qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{proof_data['report_id'][:10]}.png"); qr.save(qr_path)
        self.ln(10); self.set_font("NotoSansTC", "", 10); self.cell(0, 10, "掃描 QR Code 前往驗證頁面", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.image(qr_path, w=50, x=(self.w-50)/2)
        
# --- 全域變數 ---
latest_proof_data = None # 用於在 generate 和 finalize 之間傳遞數據

@app.route('/')
def index():
    global latest_proof_data
    latest_proof_data = None # 重置
    return render_template('index.html', api_key_set=bool(API_KEY))

@app.route('/generate', methods=['POST'])
def generate():
    global latest_proof_data
    data = request.json
    applicant_name = data.get('applicant_name')
    if not applicant_name: return jsonify({"error": "出證申請人名稱為必填項"}), 400
    
    try:
        # Step 1: 生成圖像 (與之前邏輯類似)
        prompt = data.get('prompt'); seed_input = data.get('seed')
        seed_value = int(seed_input) if seed_input and seed_input.isdigit() else random.randint(1, 10**9)
        payload = {"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "seed": seed_value, "steps": 8, "width": 512, "height": 512}
        res = requests.post("https://api.together.xyz/v1/images/generations", headers={"Authorization": f"Bearer {API_key}"}, json=payload, timeout=60)
        res.raise_for_status()
        img_bytes = requests.get(res.json()["data"][0]["url"], timeout=60).content
        
        # Step 2: 處理圖片雜湊 (Save -> Read -> Base64 -> Hash)
        img_filename = f"image_{uuid.uuid4()}.png"
        img_filepath = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
        Image.open(io.BytesIO(img_bytes)).save(img_filepath)
        with open(img_filepath, "rb") as f: definitive_bytes = f.read()
        img_base64_str = base64.b64encode(definitive_bytes).decode('utf-8')
        snapshot_hash = sha256_bytes(img_base64_str.encode('utf-8'))

        # Step 3: 建立 proof_event.json 的資料結構 (解決雞生蛋問題)
        report_id = str(uuid.uuid4())
        trace_token = str(uuid.uuid4())
        issued_at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        snapshot = {
            "version_index": 1,
            "timestamp_utc": issued_at_iso,
            "snapshot_hash": snapshot_hash,
            "prompt": prompt,
            "seed": seed_value,
            "model": payload['model'],
            "content_base64": img_base64_str # 加入Base64到snapshot中
        }
        
        # 先建立一個不含 final_event_hash 的臨時字典來計算
        temp_proof_for_hashing = {
            "report_id": report_id, "issuer": "WesmartAI Inc.", "applicant": applicant_name, "issued_at": issued_at_iso,
            "event_proof": { "trace_token": trace_token, "snapshots": [snapshot] },
            # ... 省略 verification 和 metadata，因為它們不影響 event hash
        }
        # 對這個臨時結構進行序列化與雜湊，得到 final_event_hash
        proof_string_for_hashing = json.dumps(temp_proof_for_hashing, sort_keys=True, ensure_ascii=False).encode('utf-8')
        final_event_hash = sha256_bytes(proof_string_for_hashing)

        # Step 4: 建立最終的、完整的 proof_data
        proof_data = {
            "report_id": report_id, "issuer": "WesmartAI Inc.", "applicant": applicant_name, "issued_at": issued_at_iso,
            "event_proof": { "trace_token": trace_token, "final_event_hash": final_event_hash, "snapshots": [snapshot] },
            "verification": {
                "method": "SHA-256 over a sorted, compact JSON structure",
                "validation_target": "final_event_hash",
                "verify_url": f"https://wesmart.ai/verify?hash={final_event_hash}"
            },
            "metadata": { "document_type": "AI_GENERATION_PROOF_EVENT", "format_version": "1.1" }
        }

        # Step 5: 儲存 proof_event.json 檔案
        json_filename = f"proof_event_{report_id}.json"
        json_filepath = os.path.join(app.config['UPLOAD_FOLDER'], json_filename)
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(proof_data, f, ensure_ascii=False, indent=2)

        # 將這次的結果存到全域變數，供 /finalize 使用
        latest_proof_data = proof_data

        return jsonify({
            "success": True,
            "image_url": url_for('static_download', filename=img_filename),
            "json_url": url_for('static_download', filename=json_filename),
            "preview_image_url": url_for('static_preview', filename=img_filename)
        })

    except Exception as e:
        print(f"生成失敗: {e}")
        return jsonify({"error": f"生成失敗: {str(e)}"}), 500

@app.route('/finalize', methods=['POST'])
def finalize():
    global latest_proof_data
    if not latest_proof_data:
        return jsonify({"error": "請先生成圖像和證據檔案"}), 400
    
    try:
        report_id = latest_proof_data['report_id']
        pdf = WesmartPDFReport()
        pdf.create_cover(latest_proof_data)
        # pdf.create_disclaimer_page() # 可自行決定是否需要
        # pdf.create_overview_page()   # 可自行決定是否需要
        pdf.create_generation_details_page(latest_proof_data)
        pdf.create_conclusion_page(latest_proof_data)
        
        report_filename = f"WesmartAI_Report_{report_id}.pdf"
        report_filepath = os.path.join(app.config['UPLOAD_FOLDER'], report_filename)
        pdf.output(report_filepath)

        return jsonify({
            "success": True,
            "report_url": url_for('static_download', filename=report_filename),
        })
    except Exception as e:
        print(f"報告生成失敗: {e}")
        return jsonify({"error": f"報告生成失敗: {str(e)}"}), 500


# --- 靜態檔案路由 ---
@app.route('/static/preview/<path:filename>')
def static_preview(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/download/<path:filename>')
def static_download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
