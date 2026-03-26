#include "hw_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

#define TAG               "main"
#define WIFI_SSID         "HA_TEST"
#define WIFI_PASSWORD     "77777777"

#define SERVER_BASE_URL   "http://192.168.137.1:5000"
#define CMD_ENDPOINT      SERVER_BASE_URL "/command"
#define UPLOAD_ENDPOINT   SERVER_BASE_URL "/upload"
#define POLL_INTERVAL_MS  2000

static uint8_t jpg_buf[20480];

void wifi_init() {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    ESP_LOGI(TAG, "Connecting to WiFi...");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("WIFI Connected");
    ESP_LOGI(TAG, "WiFi connected, IP: %s", WiFi.localIP().toString().c_str());
}

bool poll_command() {
    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;
    http.begin(CMD_ENDPOINT);
    http.addHeader("X-Device-ID", WiFi.macAddress());  // + เพิ่ม device ID
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
    http.begin(UPLOAD_ENDPOINT);
    http.addHeader("Content-Type", "image/jpeg");
    http.addHeader("X-Device-ID", WiFi.macAddress());  // + เพิ่ม device ID

    int code = http.POST(jpg_buf, jpg_len);
    if (code == HTTP_CODE_OK) {
        ESP_LOGI(TAG, "Upload OK: %s", http.getString().c_str());
    } else {
        ESP_LOGE(TAG, "Upload failed: %d", code);
    }
    http.end();
}

void setup() {
    Serial.begin(115200);
    wifi_init();
    hw_camera_init();
    ESP_LOGI(TAG, "Setup complete");
}

void loop() {
    if (poll_command()) {
        capture_and_upload();
    }
    delay(POLL_INTERVAL_MS);
}