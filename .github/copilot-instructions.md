# BMS/EMS Communication Protocol Guidelines

BMS ↔ EMS communication using IEEE 2030.5. 對話語言一律使用**繁體中文**。

---

## 🔴 P0 — 安全紅線（違反即停止）

以下規則保護實體設備與共享程式碼庫安全。**違反任何一條必須立即停止並通知使用者。**

### Power Control 安全

完整規範：[`.github/power-control-safety.md`](power-control-safety.md)

- ❌ **絕對禁止**：直接向 PCS 發送指令、繞過模擬模式、硬編碼 PCS 端點、測試連接實際設備
- ✅ **必須遵守**：預設 `simulation_mode=True`、使用 `SafePowerController`、驗證功率限制、記錄所有請求到日誌
- **安全模式層級**：`SIMULATION`（開發）→ `DRY_RUN`（驗證）→ `PRODUCTION`（需授權 token）

### Git 安全

- ❌ **絕對禁止** `git add .` 或 `git add -A`（會把其他 agent 的改動一起提交）
- ❌ **絕對禁止** Commit 不屬於當前任務的檔案
- ✅ 必須使用 `git add <file1> <file2> ...` 明確指定
- ✅ Commit 前必須 `git diff --cached --stat` 確認暫存區只有自己的改動

---

## 📋 工作流程 Checklist

**每次收到實作任務時，依序執行。每完成一項在心中勾選。**

### 實作前

- [ ] **閱讀 `PROJECT_ANALYSIS_REPORT.md`** 了解專案架構
- [ ] **若修改既有程式碼** → grep 搜尋影響範圍：
  ```bash
  grep -rn "function_name\|ClassName" --include="*.py" .
  ```
- [ ] **搜尋 copilot_work_log**（ChromaDB），查歷史風險與相關實作：
  ```bash
  export $(grep -v '^#' .env | xargs)
  python scripts/chromadb_search.py "任務描述 + 受影響檔案"
  ```
  > ⚠️ ChromaDB 連不上？→ 記錄警告，在 commit message 加 `[no-kb]` 標記，繼續工作。
- [ ] **確認修改計畫**（含連動修改的檔案清單）

### 實作後

- [ ] **語法/型別檢查** — `py_compile` 或 `mypy`（至少確認無 SyntaxError）
- [ ] **Git commit**：
  ```bash
  git status
  git add <具體檔案>
  git diff --cached --stat
  git commit -m "<type>: <description>"
  ```
- [ ] **寫入 copilot_work_log**：
  ```bash
  export $(grep -v '^#' .env | xargs)
  python scripts/chromadb_write_log.py \
      --summary "一行摘要" \
      --files "file1.py, file2.py" \
      --tags "tag1, tag2" \
      --anchors "file.py::Class::method" \
      --rationale "決策原因" \
      --risk "已知風險" \
      --type feature
  ```
  > ⚠️ ChromaDB 連不上？→ 記錄在 commit message 中，下次補寫。
- [ ] **更新 `PROJECT_ANALYSIS_REPORT.md`**（僅功能性改動需要，bugfix/小修可跳過）
  - 只更新受影響的章節，模板參見 [`.github/report-template.md`](report-template.md)
- [ ] **重啟 Web UI**：
  ```bash
  fuser -k 5000/tcp 2>/dev/null; sleep 1
  cd /home/us2st/ieee2030.5-cold-client && source .venv/bin/activate && bms-web --debug
  ```

### Commit Message 格式

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修正 Bug |
| `refactor` | 重構（不改變行為） |
| `docs` | 文件更新 |
| `style` | 格式調整 |
| `test` | 測試相關 |

---

## 📐 開發規範

### 語言規範

- **對話與回覆語言**：繁體中文
- **Markdown 報告**：繁體中文
- **程式碼註解（docstring / comment）**：英文，格式如下：

```python
"""
Function content description.

Args:
    name (type): Parameter content description.

Returns:
    type: Return value content description.
"""
```

### 程式碼風格

- Python 3.10+ 型別標註（`T | None` 而非 `Optional[T]`）
- ORM 欄位使用 `comment` 參數描述
- 遵循現有命名慣例
- 分層架構：API → Service → Repository → Model
- 新 API 端點需遵循 `ApiResponse` 統一回應格式
- 新增模型需配合 Alembic 遷移

### Testing Guidelines

- Use mock Modbus server for unit tests
- Validate all register conversions
- Test boundary values (0, max, negative)
- Verify bitfield parsing
- Test IEEE 2030.5 XML serialization

---

## 📘 參考資料

### 技術堆疊

- 後端：FastAPI + Flask（WSGI 掛載），SQLAlchemy 2.0 async，Pydantic v2
- 資料庫：PostgreSQL + TimescaleDB
- 排程：APScheduler 3.x（AsyncIOScheduler）
- 外部 API：httpx + tenacity 重試
- 部署：Railway + Gunicorn/Uvicorn

### Web UI 啟動

```bash
# 啟動
cd /home/us2st/ieee2030.5-cold-client && source .venv/bin/activate && bms-web --debug

# 重啟
fuser -k 5000/tcp 2>/dev/null; sleep 1
cd /home/us2st/ieee2030.5-cold-client && source .venv/bin/activate && bms-web --debug
```

- 預設位址：`http://0.0.0.0:5000/`，配置檔：`config/runtime.yaml`

### 首次環境準備

```bash
cd /home/us2st/ieee2030.5-cold-client
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
```

### Protocol Reference Files

**Source files:**
- `src/bms_2030_5_client/protocols/modbus_registers.py` — RS-485 and CUBE register definitions
- `src/bms_2030_5_client/protocols/can_messages.py` — CAN 2.0B message definitions
- `src/bms_2030_5_client/protocols/ieee2030_5_protocol.py` — IEEE 2030.5 Smart Energy Profile definitions

**Protocol specification docs:**
- [RS-485 Modbus RTU + CAN 2.0B](.github/protocols/rs485-modbus.md) — BMS V1.7 registers, CAN bus definitions
- [CUBE Modbus TCP/IP](.github/protocols/cube-modbus.md) — System/Rack registers, address offset rules

### IEEE 2030.5 規範查詢

ChromaDB `ieee2030_5` collection 是 IEEE 2030.5 規範查詢的唯一入口：

```bash
export $(grep -v '^#' .env | xargs)
python scripts/chromadb_search.py "DERProgram resource structure" --collection ieee2030_5
```

在程式碼註解中引用章節號（如 `Section 10.10`）。不直接引用靜態 `.md` 文件作為 IEEE 2030.5 規範依據。

### 外部整合 API 參考

編寫與本 Client 串接的外部程式時，參考 [COPILOT_INTEGRATION_REFERENCE.md](COPILOT_INTEGRATION_REFERENCE.md)。

### ChromaDB 連線資訊

- **Server**: `https://{CHROMA_HOST}`（環境變數）
- **認證**: Bearer Token（`CHROMA_AUTH_TOKEN` 環境變數）
- **Token 禁止寫死在程式碼中**，從 `.env` 讀取

**連線方式**（依優先順序）：
1. 環境變數 `CHROMA_HOST` + `CHROMA_AUTH_TOKEN`
2. 專案 `.env` 檔（已加入 `.gitignore`）
3. GCP Secret Manager fallback：
   ```bash
   gcloud secrets versions access latest --secret=CHROMA_HOST --project=xenon-raceway-442501-a8
   ```

**Helper 腳本**（取代 inline Python）：
- `scripts/chromadb_search.py "query"` — 搜尋知識庫
- `scripts/chromadb_write_log.py --summary "..." --files "..." --tags "..."` — 寫入工作紀錄

詳細寫入格式與 metadata 欄位定義見 [`.github/report-template.md`](report-template.md)。