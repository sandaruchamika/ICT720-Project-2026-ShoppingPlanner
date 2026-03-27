#include "hw_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <Preferences.h>

#define TAG               "main"
#define POLL_INTERVAL_MS  2000
#define RECONNECT_MS      5000   // ลอง reconnect ทุก 5 วิ ถ้า WiFi หลุด
#define AP_SSID           "ESP32-Config"
#define AP_PASSWORD       "12345678"

static uint8_t   jpg_buf[20480];
static String    g_ssid, g_password, g_server_ip;
static WebServer server(80);
Preferences      prefs;
static uint32_t  last_reconnect_ms = 0;

// ─── HTML Pages ────────────────────────────────────────────────────────────
const char CONFIG_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32 Config</title>
<style>
  body{font-family:sans-serif;max-width:400px;margin:40px auto;padding:0 20px}
  input,select{width:100%;padding:8px;margin:6px 0 16px;box-sizing:border-box;
               border:1px solid #ccc;border-radius:4px;font-size:15px;background:#fff}
  .btn{width:100%;padding:10px;border:none;border-radius:4px;font-size:16px;cursor:pointer;color:#fff}
  .btn-save{background:#2196F3} .btn-save:hover{background:#1976D2}
  .btn-scan{background:#607D8B;font-size:13px;padding:7px;margin-bottom:6px}
  .btn-scan:hover{background:#455A64}
  h2{color:#333}
  .status{padding:10px;border-radius:4px;margin-bottom:16px;font-size:14px}
  .connected{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7}
  .disconnected{background:#fce4ec;color:#c62828;border:1px solid #ef9a9a}
  .rssi{font-size:12px;color:#888;margin-left:4px}
</style>
</head><body>
<h2>⚙️ ESP32 Config</h2>
<div class="status %STATUS_CLASS%">%STATUS_MSG%</div>
<form action="/save" method="POST">
  <label>WiFi SSID</label>
  <button type="button" class="btn btn-scan" onclick="scanWifi()">🔍 Scan Networks</button>
  <select id="ssid-select" onchange="document.getElementById('ssid-input').value=this.value">
    <option value="">-- Select from scan --</option>
    %SCAN_OPTIONS%
  </select>
  <input id="ssid-input" name="ssid" value="%SSID%" placeholder="Or type manually" required>
  <label>WiFi Password</label>
  <input name="pass" type="password" placeholder="(leave blank to keep current)">
  <label>Server IP:Port</label>
  <input name="server" value="%SERVER%" placeholder="192.168.137.1:5000" required>
  <button class="btn btn-save" type="submit">💾 Save &amp; Apply</button>
</form>
<script>
function scanWifi() {
  var btn = document.querySelector('.btn-scan');
  btn.textContent = '⏳ Scanning...';
  btn.disabled = true;
  fetch('/scan').then(r => r.json()).then(data => {
    var sel = document.getElementById('ssid-select');
    sel.innerHTML = '<option value="">-- Select network --</option>';
    data.forEach(function(n) {
      var opt = document.createElement('option');
      opt.value = n.ssid;
      opt.textContent = n.ssid + ' (' + n.rssi + ' dBm)';
      sel.appendChild(opt);
    });
    btn.textContent = '🔍 Scan Networks';
    btn.disabled = false;
  }).catch(() => {
    btn.textContent = '🔍 Scan Networks';
    btn.disabled = false;
  });
}
</script>
</body></html>
)rawliteral";

const char SAVED_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="3;url=/">
<title>Saved</title>
<style>body{font-family:sans-serif;text-align:center;margin-top:80px;color:#333}</style>
</head><body>
<h2>✅ Saved!</h2>
<p>ESP32 is applying new config...</p>
<p><small>Redirecting back in 3s...</small></p>
</body></html>
)rawliteral";

// ─── NVS helpers ───────────────────────────────────────────────────────────
bool load_config() {
    prefs.begin("wifi-cfg", true);
    g_ssid      = prefs.getString("ssid",   "");
    g_password  = prefs.getString("pass",   "");
    g_server_ip = prefs.getString("server", "");
    prefs.end();
    return (g_ssid.length() > 0 && g_server_ip.length() > 0);
}

void save_config(const String& ssid, const String& pass, const String& server) {
    prefs.begin("wifi-cfg", false);
    prefs.putString("ssid",   ssid);
    prefs.putString("pass",   pass);
    prefs.putString("server", server);
    prefs.end();
}

// ─── WiFi Connect (non-blocking) ──────────────────────────────────────────
void wifi_connect() {
    if (g_ssid.length() == 0) return;
    ESP_LOGI(TAG, "Connecting to %s ...", g_ssid.c_str());
    WiFi.begin(g_ssid.c_str(), g_password.c_str());
}

// ─── Reconnect loop (เรียกใน loop()) ─────────────────────────────────────
void wifi_reconnect_if_needed() {
    if (WiFi.status() == WL_CONNECTED) return;
    if (g_ssid.length() == 0) return;

    uint32_t now = millis();
    if (now - last_reconnect_ms >= RECONNECT_MS) {
        last_reconnect_ms = now;
        ESP_LOGW(TAG, "WiFi disconnected, retrying %s ...", g_ssid.c_str());
        WiFi.disconnect();
        WiFi.begin(g_ssid.c_str(), g_password.c_str());
    }
}

// ─── Web Server ────────────────────────────────────────────────────────────
void setup_webserver() {
    // หน้า config หลัก
    server.on("/", HTTP_GET, []() {
        bool connected = (WiFi.status() == WL_CONNECTED);
        String html = String(CONFIG_HTML);
        html.replace("%SSID%",         g_ssid);
        html.replace("%SERVER%",       g_server_ip);
        html.replace("%STATUS_CLASS%", connected ? "connected" : "disconnected");
        html.replace("%STATUS_MSG%",   connected
            ? "✅ Connected: " + WiFi.localIP().toString()
            : "❌ Not connected" + (g_ssid.length() ? " (retrying: " + g_ssid + ")" : ""));
        html.replace("%SCAN_OPTIONS%", "");  // ว่างไว้ให้ JS scan เอง
        server.send(200, "text/html", html);
    });

    // Scan WiFi → return JSON
    server.on("/scan", HTTP_GET, []() {
        int n = WiFi.scanNetworks(false, true);  // async=false, show_hidden=true
        String json = "[";
        for (int i = 0; i < n; i++) {
            if (i > 0) json += ",";
            json += "{\"ssid\":\"" + WiFi.SSID(i) + "\","
                    "\"rssi\":"   + String(WiFi.RSSI(i)) + "}";
        }
        json += "]";
        WiFi.scanDelete();
        server.send(200, "application/json", json);
    });

    // Save config
    server.on("/save", HTTP_POST, []() {
        String ssid = server.arg("ssid");
        String pass = server.arg("pass");
        String srv  = server.arg("server");

        if (ssid.length() == 0 || srv.length() == 0) {
            server.send(400, "text/plain", "Missing SSID or server");
            return;
        }
        if (pass.length() == 0) pass = g_password;

        save_config(ssid, pass, srv);
        g_ssid      = ssid;
        g_password  = pass;
        g_server_ip = srv;

        server.send(200, "text/html", SAVED_HTML);

        WiFi.disconnect();
        delay(200);
        wifi_connect();
        last_reconnect_ms = millis();
    });

    server.onNotFound([]() {
        server.sendHeader("Location", "http://192.168.0.1", true);
        server.send(302, "text/plain", "");
    });

    server.begin();
    ESP_LOGI(TAG, "Web server: http://192.168.0.1 (AP) | http://%s (STA)",
             WiFi.localIP().toString().c_str());
}

// ─── HTTP helpers ──────────────────────────────────────────────────────────
String cmd_url()    { return "http://" + g_server_ip + "/command"; }
String upload_url() { return "http://" + g_server_ip + "/upload";  }

bool poll_command() {
    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;
    http.begin(cmd_url());
    http.addHeader("X-Device-ID", WiFi.macAddress());
    int code = http.GET();

    bool should_capture = false;
    if (code == HTTP_CODE_OK) {
        String body = http.getString();
        body.trim();
        ESP_LOGI(TAG, "Command: %s", body.c_str());
        should_capture = (body == "capture");
    } else {
        ESP_LOGE(TAG, "GET /command failed: %d", code);
    }
    http.end();
    return should_capture;
}

void capture_and_upload() {
    uint32_t jpg_len = hw_camera_jpg_snapshot(jpg_buf);
    if (jpg_len == 0) {
        ESP_LOGE(TAG, "Snapshot failed");
        return;
    }
    ESP_LOGI(TAG, "Snapshot OK: %u bytes", jpg_len);
    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;
    http.begin(upload_url());
    http.addHeader("Content-Type", "image/jpeg");
    http.addHeader("X-Device-ID", WiFi.macAddress());
    int code = http.POST(jpg_buf, jpg_len);
    if (code == HTTP_CODE_OK) {
        ESP_LOGI(TAG, "Upload OK: %s", http.getString().c_str());
    } else {
        ESP_LOGE(TAG, "Upload failed: %d", code);
    }
    http.end();
}

// ─── Setup / Loop ──────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    WiFi.mode(WIFI_AP_STA);

    IPAddress ap_ip(192, 168, 0, 1);
    IPAddress ap_gw(192, 168, 0, 1);
    IPAddress ap_subnet(255, 255, 255, 0);
    WiFi.softAPConfig(ap_ip, ap_gw, ap_subnet);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    ESP_LOGI(TAG, "AP started: %s  →  http://192.168.0.1", AP_SSID);

    load_config();
    wifi_connect();
    setup_webserver();
    hw_camera_init();

    ESP_LOGI(TAG, "Setup complete");
}

void loop() {
    server.handleClient();
    wifi_reconnect_if_needed();   // reconnect ตลอดถ้า WiFi หลุด

    if (poll_command()) {
        capture_and_upload();
    }
    delay(POLL_INTERVAL_MS);
}