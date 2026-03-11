#!/bin/bash
#
# BMS 2030.5 Web UI Service 安裝腳本
#
# 使用方式:
#   sudo ./scripts/install-bms-web-service.sh
#
# 這個腳本會:
# 1. 安裝 Python 套件 (包含 bms-web entry point)
# 2. 複製 systemd service 檔案
# 3. 啟用並啟動服務
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="bms-web"
SERVICE_FILE="$PROJECT_DIR/config/$SERVICE_NAME.service"

echo "=========================================="
echo "BMS 2030.5 Web UI Service Installer"
echo "=========================================="
echo ""

# 檢查是否為 root
if [ "$EUID" -ne 0 ]; then
    echo "請使用 sudo 執行此腳本"
    echo "  sudo $0"
    exit 1
fi

# 取得實際使用者
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

echo "Project directory: $PROJECT_DIR"
echo "Service file: $SERVICE_FILE"
echo "User: $REAL_USER"
echo ""

# 步驟 1: 安裝 Python 套件
echo "[1/4] Installing Python package..."
cd "$PROJECT_DIR"
sudo -u "$REAL_USER" pip install --user -e .
echo "Done."
echo ""

# 步驟 2: 確認 entry point 存在
echo "[2/4] Verifying bms-web command..."
if sudo -u "$REAL_USER" bash -c "command -v bms-web" &> /dev/null; then
    BMS_WEB_PATH=$(sudo -u "$REAL_USER" bash -c "which bms-web")
    echo "Found: $BMS_WEB_PATH"
else
    echo "Warning: bms-web not found in PATH"
    echo "Trying common locations..."
    BMS_WEB_PATH="$REAL_HOME/.local/bin/bms-web"
    if [ -f "$BMS_WEB_PATH" ]; then
        echo "Found: $BMS_WEB_PATH"
    else
        echo "Error: bms-web not found"
        exit 1
    fi
fi
echo ""

# 步驟 3: 更新並複製 service 檔案
echo "[3/4] Installing systemd service..."

# 創建必要目錄
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/data"
chown "$REAL_USER:$REAL_USER" "$PROJECT_DIR/logs"
chown "$REAL_USER:$REAL_USER" "$PROJECT_DIR/data"

# 更新 service 檔案中的路徑
TEMP_SERVICE="/tmp/$SERVICE_NAME.service"
sed -e "s|/home/coldelectric|$REAL_HOME|g" \
    -e "s|ExecStart=.*|ExecStart=$BMS_WEB_PATH|" \
    -e "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|" \
    -e "s|ReadWritePaths=.*|ReadWritePaths=$PROJECT_DIR/logs $PROJECT_DIR/data|" \
    -e "s|User=.*|User=$REAL_USER|" \
    -e "s|Group=.*|Group=$REAL_USER|" \
    -e "s|Environment=\"PYTHONPATH=.*\"|Environment=\"PYTHONPATH=$PROJECT_DIR/src\"|" \
    "$SERVICE_FILE" > "$TEMP_SERVICE"

# 複製到 systemd 目錄
cp "$TEMP_SERVICE" /etc/systemd/system/$SERVICE_NAME.service
rm "$TEMP_SERVICE"

# 重新載入 systemd
systemctl daemon-reload
echo "Done."
echo ""

# 步驟 4: 啟用並啟動服務
echo "[4/4] Enabling and starting service..."
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME
echo "Done."
echo ""

# 顯示狀態
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Service status:"
systemctl status $SERVICE_NAME --no-pager
echo ""
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME   # 查看狀態"
echo "  sudo systemctl restart $SERVICE_NAME  # 重啟服務"
echo "  sudo systemctl stop $SERVICE_NAME     # 停止服務"
echo "  sudo journalctl -u $SERVICE_NAME -f   # 查看日誌"
echo ""
echo "Web UI: http://localhost:5000"
echo ""
