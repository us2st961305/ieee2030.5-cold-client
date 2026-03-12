# PROJECT_ANALYSIS_REPORT.md 模板

> 此模板供 Agent 更新 `PROJECT_ANALYSIS_REPORT.md` 時參考。
> 僅更新受影響的章節，不需要每次全部重寫。

---

## 1. 專案概述
- 專案的主要功能和目的
- 使用的程式語言和主要技術堆疊

## 2. 程式碼結構分析
- 主要目錄結構及其用途
- 關鍵原始碼檔案及其作用
- 程式碼組織模式（設計模式、架構模式等）
- 模組化程度評估

## 3. 功能圖
- 核心功能清單及描述
- 功能之間的關係和互動方式（Mermaid 圖）
- 使用者流程圖（如適用）
- API 介面分析（如適用）

## 4. 依賴關係分析
- 外部依賴函式庫清單及用途
- 內部模組間依賴關係圖
- 依賴更新頻率和維護狀況
- 潛在的依賴風險評估

## 5. 程式碼品質評估
- 程式碼可讀性
- 註解和文件完整性
- 測試覆蓋率
- 潛在的程式碼異味和改進空間

## 6. 關鍵演算法與資料結構
- 專案中使用的主要演算法分析
- 關鍵資料結構及其設計原理
- 效能關鍵點分析

## 7. 函數呼叫圖
- 主要函數/方法列表
- 函數呼叫關係視覺化（Mermaid 圖）
- 高頻呼叫路徑分析
- 遞歸和複雜呼叫鏈識別

## 8. 安全性分析
- 潛在的安全漏洞
- 敏感資料處理方式
- 認證和授權機制評估

## 9. 可擴展性和效能
- 擴展設計評估
- 效能瓶頸識別
- 並發處理機制分析

## 10. 總結與建議
- 專案整體品質評價
- 主要優勢和特色
- 潛在改進點和建議
- 適用場景推薦

---

## copilot_work_log 寫入格式

### Document 結構化文字

```
[專案名稱] 實作摘要

## Code Anchors
- file.py::ClassName::method_name
- another.py::helper_function

## Dependencies Affected
- src/module_a.py
- src/module_b.py

## Decision Rationale
選擇這個方法的原因...

## Risk Notes
已知風險或踩坑經驗...

## Details
詳細實作說明...
Files: file1.py, file2.py
Tags: tag1, tag2
```

### Metadata 欄位（共 12 個）

| 欄位 | 說明 | 範例 |
|------|------|------|
| `project_name` | 專案名稱 | `ieee2030.5-cold-client` |
| `project_path` | 專案路徑 | `/home/us2st/ieee2030.5-cold-client` |
| `summary` | 一行摘要 | `Add Modbus degraded state` |
| `files_changed` | 修改的檔案 | `file1.py, file2.py` |
| `tags` | 標籤 | `modbus, reconnection` |
| `github_repo` | GitHub repo | `owner/repo` |
| `timestamp` | UTC 時間戳 | `datetime.now(timezone.utc).isoformat()` |
| `code_anchors` | 函數級錨點 | `file.py::Class::method` |
| `dependencies_affected` | 受影響模組 | `module_a.py, module_b.py` |
| `decision_rationale` | 決策原因 | `為什麼選擇這個做法` |
| `risk_notes` | 風險紀錄 | `已知風險或踩坑經驗` |
| `change_type` | 變更類型 | `feature` / `bugfix` / `refactor` / `config` |

### code_anchors 格式
- Python: `file.py::ClassName::method_name` 或 `file.py::function_name`
- TypeScript: `file.ts::ClassName.methodName` 或 `file.ts::functionName`
- 每個被修改的函數/方法都應列出
