# ICT720 Smart Shopping Planner — 2026 

A full-stack IoT system that uses an ESP32-S3 camera, a Python backend, Google Gemini Vision AI, and a Telegram bot to intelligently analyse fridge contents and generate shopping suggestions.

---

## Table of Contents

- [Scope and Objectives](#scope-and-objectives)
- [User Stories](#user-stories)
- [System Architecture](#system-architecture)
- [Module Breakdown](#module-breakdown)
- [Data Flow](#data-flow)
- [Tools and Technologies](#tools-and-technologies)
- [Design Patterns](#design-patterns)
- [Features](#features)
- [Project Structure](#project-structure)
- [Setup and Deployment](#setup-and-deployment)
- [Environment Variables](#environment-variables)
- [Team Roles](#team-roles)

---

## Scope and Objectives

### Scope

This project develops a smart kitchen assistant that captures images of a fridge using an IoT camera device, analyses the contents with an LLM Vision API, and returns structured insights to the user via a Telegram bot or web interface. The system covers:

- Embedded firmware for the LilyGO T-SimCam / ESP32-S3-Box device
- A centralised Python/Flask backend server
- Google Gemini 2.5 Flash Vision AI integration
- A MongoDB database for persisting scan history
- A Telegram bot as the primary user interface

### Objectives

1. Enable remote image capture from the ESP32-S3 camera via Telegram commands or a web UI.
2. Automatically analyse captured fridge images using an LLM and extract structured data (inventory, shopping needs, meal ideas).
3. Persist analysis history in a database and surface it through query APIs.
4. Provide a convenient Telegram bot interface with commands for inventory, shopping suggestions, dish checks, and scheduled reports.
5. Deploy all services as Docker containers for portability and reproducibility.

---

## User Stories

### Current — Implemented in this Release

| ID | As a user, I want to... | So that... | Telegram Command |
|---|---|---|---|
| US-01 | take a photo of my fridge via Telegram | the system can identify all visible items without me manually listing them | `/list` |
| US-02 | have the system detect item categories (e.g. milk, eggs, vegetables) | I understand the type and variety of what I currently have | `/list` |
| US-03 | have the system count how many items of each type are present | I can track quantities and spot what is running low | `/list` |
| US-04 | ask "What can I cook?" | I get meal ideas based only on what is already available in my fridge | `/meals` via Web | 
| US-05 | get recipe suggestions using only available ingredients | I can minimise food waste and avoid unnecessary shopping | `/meals` via Web |
| US-06 | see the missing ingredients for a specific recipe | I know exactly what to buy before I start cooking | `/suggest <dish>` |
| US-07 | set scheduled reminders to scan my fridge | my inventory stays updated regularly without me having to remember | `/subscribe HH:MM` |

---

### Future — Planned for Next Release

| ID | As a user, I want to... | So that... | Notes |
|---|---|---|---|
| US-08 | have the system suggest items I need to buy | I do not forget essentials when I go grocery shopping | Extends current shopping suggestion with smarter gap detection |
| US-09 | have low-stock items automatically added to a running shopping list | I always have an up-to-date list ready without manually tracking items | Requires persistent per-user shopping list storage |
| US-10 | receive recommendations based on my past cooking habits | suggestions improve over time and reflect what I actually cook | Requires analysis history mining and user preference modelling |

---

## System Architecture


![Shopping Planner Model Architecture](https://github.com/user-attachments/assets/0d8f72a0-a091-4b7c-8ec7-395e8862c6f0)


---

## Module Breakdown

### 1. ESP32-S3 Firmware (`firmware/`)

- Programs the LilyGO T-SimCam / ESP32-S3-Box to operate in dual WiFi mode (AP for configuration, STA for server connectivity).
- Polls the Flask server every 2 seconds for a `capture` command.
- On command received: captures a JPEG image using the OV2640 sensor and HTTP-POSTs it to `/upload` on the Flask server.
- Provides a web configuration UI at `192.168.0.1` for WiFi credentials and server IP setup.
- Stores settings persistently in NVS (Non-Volatile Storage).

### 2. Central Python Server (`server/`)

- Flask application serving as the hub of the system.
- Exposes REST endpoints: `/trigger`, `/command`, `/upload`, `/latest-image`, `/analyse`, `/history`.
- Stores received images to the `captures/` directory with Unix timestamp filenames.
- Spawns background daemon threads for non-blocking LLM analysis.
- Uses threading locks for thread-safe shared state management.
- Integrates with Google Gemini via `google-genai` SDK.
- Persists analysis results to MongoDB via the `Motor` async driver.
- Serves an embedded HTML web UI for manual triggering and result viewing.

### 3. AI / LLM Integration (`server/app/services/llm.py`)

- Constructs structured prompts for four distinct analysis modes.
- Submits images to the Google Gemini 2.5 Flash Vision API.
- Parses raw LLM output into validated JSON data structures for downstream consumption.
- Analysis modes:
  - **Fridge Inventory** — list of all visible items with type and quantity.
  - **Meal Suggestions** — recipes derivable from visible ingredients.
  - **Dish Check** — whether a specific dish can be made with current contents.

### 4. Database Layer (MongoDB, accessed via `server/`)

- MongoDB 7 database (`shoppingplanner`) with authenticated access.
- Collection `analyses` stores: timestamp, analysis mode, dish (if applicable), and full JSON result.
- Motor (async) driver used for non-blocking database writes.
- Query APIs exposed via Flask endpoints for the bot and web UI to retrieve history.

### 5. Telegram Bot (`telegram-bot/bot.py`)

- Built with `python-telegram-bot` v20 (async/await).
- Communicates with the Flask server via `httpx` HTTP calls.
- Handles all user interaction: triggering captures, displaying results, managing subscriptions.
- Supports scheduled weekly reports (Saturday, configurable time) per user via the job queue.
- Thai timezone awareness (Asia/Bangkok) and emoji-rich formatted messages.

---

## Data Flow

![Data Flow](https://github.com/user-attachments/assets/6267c15f-ec82-4120-a628-8eb097f02c5e)


---

## Tools and Technologies

| Layer | Technology | Version / Notes |
|---|---|---|
| Firmware | C++ / PlatformIO | Arduino framework, ESP32-S3 |
| Camera | OV2640 | JPEG capture, PSRAM buffered |
| Backend | Python / Flask | 3.12, REST API + WebUI |
| AI Vision | Google Gemini | 2.5 Flash, `google-genai` SDK |
| Database | MongoDB | v7, Motor async driver |
| Telegram Bot | python-telegram-bot | v20.8, async, job-queue |
| HTTP Client | httpx | Async HTTP for bot-server comms |
| Image Handling | Pillow (PIL) | Server-side image processing |
| Containerisation | Docker / Docker Compose | 3 services: server, bot, mongo |
| Config | python-dotenv | `.env`-based secrets management |
| Timezone | pytz | Bangkok (Asia/Bangkok) |

---

## Design Patterns

### Command Pattern (IoT Polling)
The ESP32 does not receive push notifications. Instead it actively polls `GET /command` every 2 seconds. The Flask server sets a command string (`"capture"` or `""`) which the device reads and acts upon. This avoids NAT traversal issues and is robust for embedded devices.

### Producer-Consumer
The ESP32 (producer) captures and uploads images independently. The Flask server (consumer) processes them in background threads. Decoupling via shared state and locks prevents blocking.

### Observer / Polling for Results
The web UI and Telegram bot poll `GET /latest-image` and `GET /analyse` endpoints to check for new analysis results, avoiding the need for WebSockets while remaining responsive.

### Thread-Safe State Machine
Flask uses Python threading locks to protect shared mutable state (`_command`, `_latest_image`, `_last_ts`, `_last_analysis`). This enables safe concurrent access from multiple request threads and background LLM threads.

### Strategy Pattern (LLM Modes)
The `llm.py` service selects different prompt strategies at runtime depending on the requested analysis mode. Each mode produces a different structured JSON schema from the same image input.

### MVC (Model-View-Controller)
Flask separates routing (controller), MongoDB documents (model), and the embedded HTML UI / Telegram formatted messages (view).

### Repository Pattern (Database)
Database access is encapsulated in server-side service functions, exposing clean query APIs to the bot and web UI rather than raw MongoDB queries.

---

## Features

### Camera & Image Capture
- Remote capture triggered via Telegram command or web button
- Dual-mode WiFi (AP for device setup + STA for connectivity)
- Web configuration interface at `192.168.0.1` (SSID: `ESP32-Config`)
- Persistent credential storage in device NVS
- JPEG images stored with Unix timestamp filenames

### AI Vision Analysis (4 Modes)
| Mode | Command | Output |
|---|---|---|
| Fridge Inventory | `/list` | JSON array: `[{name, type, count}]` |
| Shopping Suggestions | `/suggest` | JSON: `{low_stock, recommended_to_buy, tip}` |
| Meal Ideas | `/meals` | JSON: `{available_ingredients, meals[], fun_fact}` |
| Dish Check | `/suggest <dish>` | JSON: `{dish, available_for_dish, missing[], can_make, tip}` |

### Telegram Bot Commands
| Command | Description |
|---|---|
| `/start` | Show help and available commands |
| `/image` | Capture and send raw photo |
| `/list` | Capture and show fridge inventory |
| `/suggest <dish>` | Check if a specific dish can be made |
| `/subscribe HH:MM` | Schedule weekly Saturday report |
| `/unsubscribe` | Cancel scheduled reports |
| `/jobs` | View your active scheduled jobs |

### Web Interface
- Real-time image display after capture
- Mode selector (Inventory / Shopping / Meals / Dish Check)
- Live AI analysis viewer with loading indicator
- Re-analyse same image in a different mode without re-capture
- Thai-language UI with dark theme

### Database & History
- All analyses persisted to MongoDB with timestamps
- Mode and dish tracking per scan
- History queryable via REST API
- Weekly scheduled reports from stored data

### Scheduled Reports
- Per-user Saturday reports at user-specified time
- Bangkok timezone (Asia/Bangkok) aware scheduling
- Job queue managed by `python-telegram-bot` built-in scheduler

---

## Project Structure

```
ICT720-Project-2026-ShoppingPlanner/
├── docker-compose.yml           # Orchestrates all 3 services
├── .gitignore
├── LICENSE
│
├── firmware/                    # ESP32-S3 camera firmware
│   ├── platformio.ini           # PlatformIO board config
│   ├── include/
│   │   ├── main.h
│   │   ├── hw_camera.h
│   │   └── openmvrpc.h
│   └── src/
│       ├── main.cpp             # WiFi, HTTP polling, capture logic
│       └── hw_camera.cpp        # OV2640 camera driver
│
├── server/                      # Central Flask backend
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # Flask routes, state manager, WebUI
│       └── services/
│           └── llm.py           # Gemini Vision API integration
│
├── telegram-bot/                # Telegram user interface
│   ├── Dockerfile
│   ├── requirements.txt
│   └── bot.py                   # Async bot handlers and scheduler
│
└── infra/
    └── .env                     # Environment secrets (not committed)
```

---

## Setup and Deployment

### Prerequisites
- Docker and Docker Compose installed
- Google Gemini API key
- Telegram Bot token (from @BotFather)
- ESP32-S3-Box hardware + PlatformIO for firmware flashing

### 1. Configure Environment

Create `infra/.env`:

```env
GEMINI_API_KEY=your_gemini_api_key
MONGO_URI=mongodb://admin:password@mongo:27017/shoppingplanner?authSource=admin
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
FLASK_URL=http://server:5000
```

### 2. Start Backend Services

```bash
docker-compose up --build
```

This starts:
- `mongo` — MongoDB 7 on port `27017`
- `server` — Flask API + WebUI on port `5000`
- `telegram-bot` — Telegram bot (internal, no exposed port)

### 3. Flash Firmware

```bash
cd firmware
pio run --target upload
```

Power on the device. Connect to WiFi SSID `ESP32-Config` (password: `12345678`) and navigate to `http://192.168.0.1` to configure your home WiFi credentials and the Flask server IP.

### 4. Use the Bot

Open Telegram, find your bot, and send `/start`.

---

## Environment Variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini Vision API key |
| `MONGO_URI` | MongoDB connection string with credentials |
| `TELEGRAM_BOT_TOKEN` | Token from Telegram @BotFather |
| `FLASK_URL` | Internal Docker URL to the Flask server |

---

## Team Roles

Sophea Seng: Hardware & Embedded Engineer : Set up and program the LilyGO T-SimCam ESP32-S3 to connect to Wi-Fi, capture a photo when triggered, and send the image to the Python server.

Pornpipat Varin: Backend API Developer : Build the central Python server that receives images from ESP32, routes them to the LLM, returns results, and connects all system components together.

Siriviti Mohottige Sandaru Chamika Nanayakkara: AI / LLM Integration Engineer : Design prompts and integrate the LLM Vision API to analyze bottle images, then parse the output into clean structured data for the rest of the system to use.

Myat Yi Aung: Database Engineer: Design and manage the database to store scan history, detected bottle data, and shopping suggestions — and provide query APIs for other modules to access.

Ploypilin Prutpinit: Telegram Bot Developer : Build the Telegram Bot as the user interface — handling user commands, triggering the camera, and sending back analysis results and shopping suggestions.


