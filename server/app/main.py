import os
import time
from io import BytesIO
from pathlib import Path
from threading import Lock, Thread

from flask import Flask, request, jsonify, send_file, render_template_string

from services.llm import analyze_image

app = Flask(__name__)

# ── state ──────────────────────────────────────────────────────────────────
_lock         = Lock()
_command      = "idle"
_latest_image = None
_last_ts      = None
_last_analysis = None   # ← เพิ่ม

SAVE_DIR = Path("captures")
SAVE_DIR.mkdir(exist_ok=True)

# ── HTML ───────────────────────────────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vision Cam</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: sans-serif; background: #111; color: #eee;
           display: flex; flex-direction: column; align-items: center;
           min-height: 100vh; padding: 2rem 1rem; gap: 1.2rem; }
    h1   { font-size: 1.4rem; font-weight: 500; }
    #img-box { width: 100%; max-width: 640px; aspect-ratio: 4/3;
               background: #222; border-radius: 12px; overflow: hidden;
               display: flex; align-items: center; justify-content: center; }
    #img-box img { width: 100%; height: 100%; object-fit: contain; }
    #placeholder { color: #555; font-size: 0.9rem; }
    #ts     { font-size: 0.8rem; color: #888; }
    #status { font-size: 0.85rem; color: #aaa; min-height: 1.2em; }

    /* Analysis box */
    #analysis-box {
      width: 100%; max-width: 640px;
      background: #1a1a2e; border: 1px solid #333;
      border-radius: 12px; padding: 1rem 1.2rem;
      display: none; gap: 0.5rem; flex-direction: column;
    }
    #analysis-box.visible { display: flex; }
    #analysis-title { font-size: 0.75rem; color: #4f8ef7;
                      text-transform: uppercase; letter-spacing: .05em; }
    #analysis-text  { font-size: 0.9rem; color: #ddd; line-height: 1.6;
                      white-space: pre-wrap; }
    #analysis-loader { font-size: 0.85rem; color: #888;
                       display: none; font-style: italic; }

    /* Controls */
    .controls { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap;
                justify-content: center; }
    select { padding: 0.6rem 1rem; border-radius: 8px; border: 1px solid #444;
             background: #222; color: #eee; font-size: 0.9rem; cursor: pointer; }
    .btn  { padding: 0.75rem 2rem; border-radius: 8px; border: none;
            font-size: 1rem; cursor: pointer; transition: opacity .15s; }
    .btn:hover { opacity: 0.85; }
    #btn-capture  { background: #4f8ef7; color: #fff; }
    #btn-reanalyze { background: #2a2a3e; color: #aaa;
                     border: 1px solid #444; font-size: 0.85rem;
                     padding: 0.6rem 1.2rem; display: none; }
    #btn-reanalyze.visible { display: inline-block; }
  </style>
</head>
<body>
  <h1>Vision Cam — LilyGO T-SimCam</h1>

  <div id="img-box">
    <img id="photo" src="" alt="" style="display:none">
    <span id="placeholder">ยังไม่มีภาพ — กด Capture</span>
  </div>

  <span id="ts"></span>

  <div class="controls">
    <select id="mode-select">
      <option value="general">General</option>
      <option value="security">Security</option>
      <option value="shopping">Shopping</option>
      <option value="thai">ภาษาไทย</option>
    </select>
    <button class="btn" id="btn-capture" onclick="sendCapture()">Capture</button>
    <button class="btn" id="btn-reanalyze" onclick="reanalyze()">Re-analyze</button>
  </div>

  <span id="status"></span>

  <div id="analysis-box">
    <span id="analysis-title">AI Analysis</span>
    <span id="analysis-loader">กำลังวิเคราะห์...</span>
    <span id="analysis-text"></span>
  </div>

  <script>
    function setStatus(msg) {
      document.getElementById('status').textContent = msg;
    }

    function showAnalysis(text) {
      const box    = document.getElementById('analysis-box');
      const loader = document.getElementById('analysis-loader');
      const result = document.getElementById('analysis-text');
      loader.style.display = 'none';
      result.textContent   = text;
      box.classList.add('visible');
      document.getElementById('btn-reanalyze').classList.add('visible');
    }

    function showAnalysisLoading() {
      const box    = document.getElementById('analysis-box');
      const loader = document.getElementById('analysis-loader');
      const result = document.getElementById('analysis-text');
      result.textContent    = '';
      loader.style.display  = 'block';
      box.classList.add('visible');
    }

    async function sendCapture() {
      const mode = document.getElementById('mode-select').value;
      setStatus('กำลังส่งคำสั่ง...');
      await fetch('/trigger', { method: 'POST' });
      setStatus('รอ device ถ่ายภาพ...');
      pollImage(mode);
    }

    async function reanalyze() {
      const mode = document.getElementById('mode-select').value;
      showAnalysisLoading();
      setStatus('กำลังวิเคราะห์ใหม่...');
      const r = await fetch('/reanalyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      const j = await r.json();
      showAnalysis(j.analysis);
      setStatus('วิเคราะห์เสร็จแล้ว');
    }

    function pollImage(mode) {
      let tries = 0;
      const iv = setInterval(async () => {
        const r = await fetch('/latest_ts');
        const j = await r.json();
        if (j.ts && j.ts !== window._lastTs) {
          window._lastTs = j.ts;

          // show image
          document.getElementById('photo').src = '/latest_image?t=' + j.ts;
          document.getElementById('photo').style.display = 'block';
          document.getElementById('placeholder').style.display = 'none';
          document.getElementById('ts').textContent =
            'ถ่ายเมื่อ ' + new Date(j.ts * 1000).toLocaleTimeString('th-TH');
          setStatus('ได้รับภาพแล้ว — กำลังวิเคราะห์...');
          clearInterval(iv);

          // show analysis loading then poll result
          showAnalysisLoading();
          pollAnalysis(j.ts);
        }
        if (++tries > 20) { clearInterval(iv); setStatus('Timeout'); }
      }, 500);
    }

    function pollAnalysis(ts) {
      let tries = 0;
      const iv = setInterval(async () => {
        const r = await fetch('/latest_analysis');
        const j = await r.json();
        if (j.analysis && j.ts === ts) {
          showAnalysis(j.analysis);
          setStatus('วิเคราะห์เสร็จแล้ว');
          clearInterval(iv);
        }
        if (++tries > 40) { clearInterval(iv); setStatus('Analysis timeout'); }
      }, 1000);
    }

    // โหลดข้อมูลล่าสุดตอนเปิดหน้า
    (async () => {
      const r = await fetch('/latest_analysis');
      const j = await r.json();
      if (j.ts) {
        window._lastTs = j.ts;
        document.getElementById('photo').src = '/latest_image?t=' + j.ts;
        document.getElementById('photo').style.display = 'block';
        document.getElementById('placeholder').style.display = 'none';
        document.getElementById('ts').textContent =
          'ถ่ายเมื่อ ' + new Date(j.ts * 1000).toLocaleTimeString('th-TH');
        if (j.analysis) showAnalysis(j.analysis);
      }
    })();
  </script>
</body>
</html>
"""

# ── routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/command", methods=["GET"])
def command():
    with _lock:
        cmd = _command
        if _command == "capture":
            globals()['_command'] = "idle"
    return cmd, 200


@app.route("/trigger", methods=["POST"])
def trigger():
    with _lock:
        globals()['_command'] = "capture"
    return jsonify({"queued": True})


@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_data()
    if not data:
        return jsonify({"error": "empty body"}), 400

    ts        = time.time()
    device_id = request.headers.get("X-Device-ID", "unknown")
    mode      = request.headers.get("X-Mode", "general")

    with _lock:
        globals()['_latest_image']  = data
        globals()['_last_ts']       = ts
        globals()['_last_analysis'] = None   # reset ระหว่างรอ

    # บันทึกไฟล์
    fname = SAVE_DIR / f"{int(ts)}.jpg"
    fname.write_bytes(data)
    print(f"[upload] {device_id}  {len(data)} bytes → {fname}")

    # วิเคราะห์ใน background thread (ไม่บล็อก response)
    def run_llm():
        print(f"[llm] analyzing mode={mode}...")
        result = analyze_image(data, mode)
        with _lock:
            globals()['_last_analysis'] = result
        print(f"[llm] done: {result[:80]}...")

    Thread(target=run_llm, daemon=True).start()

    return jsonify({"ok": True, "ts": ts})


@app.route("/reanalyze", methods=["POST"])
def reanalyze():
    """Re-analyze latest image with a different mode."""
    mode = request.json.get("mode", "general")
    with _lock:
        img = _latest_image

    if img is None:
        return jsonify({"error": "no image"}), 404

    result = analyze_image(img, mode)
    with _lock:
        globals()['_last_analysis'] = result

    return jsonify({"analysis": result})


@app.route("/latest_image")
def latest_image():
    with _lock:
        img = _latest_image
    if img is None:
        return "No image", 404
    return send_file(BytesIO(img), mimetype="image/jpeg")


@app.route("/latest_ts")
def latest_ts():
    with _lock:
        ts = _last_ts
    return jsonify({"ts": ts})


@app.route("/latest_analysis")
def latest_analysis():
    with _lock:
        ts       = _last_ts
        analysis = _last_analysis
    return jsonify({"ts": ts, "analysis": analysis})


# ── main ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)