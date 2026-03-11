"""
HTTPS Notification Server (HTTPS 通知服務器)

接收來自 IEEE 2030.5 伺服器的推送通知。

Reference: IEEE Std 2030.5-2023, Clause 8.9.3

使用方式:
    server = NotificationServer(config)
    server.set_notification_handler(handler)
    await server.start()
    # ... 運行中 ...
    await server.stop()
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional
import xml.etree.ElementTree as ET
from defusedxml.ElementTree import fromstring as _safe_fromstring

from aiohttp import web

from bms_2030_5_client.models import (
    Notification,
    NotificationStatusType,
)

logger = logging.getLogger(__name__)


@dataclass
class NotificationServerConfig:
    """HTTPS 通知服務器配置"""
    
    # 監聽設定
    host: str = "127.0.0.1"  # Loopback only; use "0.0.0.0" when server is on a different host
    port: int = 8443
    endpoint: str = "/notify"
    
    # TLS 設定 (使用與客戶端相同的憑證)
    cert_file: str = "certs/client.crt"
    key_file: str = "certs/client.key"
    ca_file: str = "certs/ca.crt"
    
    # 需要客戶端憑證驗證 (雙向 TLS)
    require_client_cert: bool = True
    
    # 是否啟用 TLS（當使用 Tailscale Funnel 等 reverse proxy 時可禁用）
    use_tls: bool = True
    
    # 服務器配置
    request_timeout_s: float = 30.0
    # 最大 XML 請求內容大小 (防止 Billion Laughs / XML bomb DoS 攻擊)
    max_xml_body_size: int = 65536  # 64 KB


# Type alias for notification callback
NotificationCallback = Callable[[Notification, str], Awaitable[None]]


class NotificationServer:
    """
    HTTPS 通知服務器
    
    接收 IEEE 2030.5 伺服器的推送通知。
    
    實作要點:
    1. HTTPS with TLS 雙向驗證
    2. 接受 POST 請求到指定端點
    3. 解析 Notification XML
    4. 回傳 HTTP 204 No Content
    
    使用方式:
        config = NotificationServerConfig(
            port=8443,
            cert_file="certs/client.crt",
            key_file="certs/client.key",
        )
        
        server = NotificationServer(config)
        server.set_notification_handler(my_handler)
        await server.start()
    """
    
    def __init__(self, config: NotificationServerConfig):
        """
        初始化通知服務器
        
        Args:
            config: 服務器配置
        """
        self.config = config
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._running = False
        
        # 通知處理回調
        self._notification_handler: Optional[NotificationCallback] = None
        
        # 統計
        self._stats = {
            "notifications_received": 0,
            "notifications_processed": 0,
            "errors": 0,
        }
    
    def set_notification_handler(
        self,
        handler: NotificationCallback
    ) -> None:
        """
        設定通知處理回調
        
        Args:
            handler: 異步回調函數，接收 (Notification, raw_xml)
        """
        self._notification_handler = handler
    
    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self._running
    
    @property
    def stats(self) -> dict:
        """取得統計資料"""
        return dict(self._stats)
    
    @property
    def notification_uri(self) -> str:
        """取得通知 URI (用於訂閱)"""
        return f"https://{self.config.host}:{self.config.port}{self.config.endpoint}"
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        """創建 SSL 上下文"""
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        
        # 載入服務器憑證和私鑰
        cert_path = Path(self.config.cert_file)
        key_path = Path(self.config.key_file)
        ca_path = Path(self.config.ca_file)
        
        if not cert_path.exists():
            raise FileNotFoundError(f"Certificate not found: {cert_path}")
        if not key_path.exists():
            raise FileNotFoundError(f"Key file not found: {key_path}")
        
        ssl_ctx.load_cert_chain(
            certfile=str(cert_path),
            keyfile=str(key_path),
        )
        
        # 載入 CA 憑證進行客戶端驗證
        if ca_path.exists():
            ssl_ctx.load_verify_locations(cafile=str(ca_path))
        
        # 設定客戶端驗證模式
        if self.config.require_client_cert:
            ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ssl_ctx.verify_mode = ssl.CERT_OPTIONAL
        
        return ssl_ctx
    
    async def _handle_notification(self, request: web.Request) -> web.Response:
        """
        處理通知請求
        
        Args:
            request: HTTP 請求
            
        Returns:
            HTTP 204 No Content (成功) 或錯誤回應
        """
        self._stats["notifications_received"] += 1
        
        try:
            # 讀取請求內容
            content_type = request.content_type
            raw_xml = await request.text()
            
            # 檢查內容大小 (防止 XML bomb DoS 攻擊)
            if len(raw_xml) > self.config.max_xml_body_size:
                logger.warning(
                    f"Notification body too large: {len(raw_xml)} bytes "
                    f"(limit: {self.config.max_xml_body_size} bytes)"
                )
                return web.Response(status=413, text="Request body too large")
            
            logger.debug(f"Received notification: {raw_xml[:200]}...")
            
            # 檢查內容類型
            if content_type not in (
                "application/sep+xml",
                "application/xml",
                "text/xml"
            ):
                logger.warning(f"Unexpected content type: {content_type}")
            
            # 解析通知
            notification = self._parse_notification(raw_xml)
            
            logger.info(
                f"Notification received: "
                f"resource={notification.subscribedResource}, "
                f"status={notification.status}"
            )
            
            # 調用處理回調
            if self._notification_handler:
                try:
                    await self._notification_handler(notification, raw_xml)
                    self._stats["notifications_processed"] += 1
                except Exception as e:
                    logger.exception(f"Notification handler error: {e}")
                    self._stats["errors"] += 1
            else:
                logger.warning("No notification handler configured")
            
            # 返回 204 No Content (IEEE 2030.5 規定)
            return web.Response(status=204)
        
        except Exception as e:
            logger.exception(f"Failed to process notification: {e}")
            self._stats["errors"] += 1
            return web.Response(
                status=400,
                text="Bad Request"
            )
    
    def _parse_notification(self, xml_str: str) -> Notification:
        """
        解析 Notification XML
        
        Args:
            xml_str: XML 字串
            
        Returns:
            Notification 物件
        """
        try:
            root = _safe_fromstring(xml_str)
            
            # 移除命名空間前綴
            def strip_ns(tag: str) -> str:
                if "}" in tag:
                    return tag.split("}")[1]
                return tag
            
            notification = Notification()
            
            for child in root:
                tag = strip_ns(child.tag)
                
                if tag == "subscribedResource":
                    notification.subscribedResource = child.text or ""
                elif tag == "newResourceURI":
                    notification.newResourceURI = child.text
                elif tag == "status":
                    notification.status = int(child.text or "0")
                elif tag == "Resource":
                    # 保存原始 Resource XML
                    notification.Resource = ET.tostring(child, encoding="unicode")
            
            return notification
        
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            raise ValueError(f"Invalid notification XML: {e}")
    
    async def start(self) -> None:
        """啟動通知服務器"""
        if self._running:
            logger.warning("Notification server already running")
            return
        
        logger.info(
            f"Starting notification server on "
            f"{self.config.host}:{self.config.port}{self.config.endpoint}"
        )
        
        # 創建 aiohttp 應用
        self._app = web.Application()
        self._app.router.add_post(
            self.config.endpoint,
            self._handle_notification
        )
        
        # 創建 SSL 上下文（僅在啟用 TLS 時）
        ssl_context = None
        if self.config.use_tls:
            try:
                ssl_context = self._create_ssl_context()
            except FileNotFoundError as e:
                logger.warning(f"TLS certificates not found: {e}, running without TLS")
                ssl_context = None
        else:
            logger.info("TLS disabled (using reverse proxy for TLS termination)")
        
        # 啟動服務器
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        
        self._site = web.TCPSite(
            self._runner,
            self.config.host,
            self.config.port,
            ssl_context=ssl_context,
        )
        await self._site.start()
        
        self._running = True
        
        protocol = "https" if ssl_context else "http"
        logger.info(
            f"Notification server started: "
            f"{protocol}://{self.config.host}:{self.config.port}{self.config.endpoint}"
        )
    
    async def stop(self) -> None:
        """停止通知服務器"""
        if not self._running:
            return
        
        logger.info("Stopping notification server...")
        
        if self._site:
            await self._site.stop()
        
        if self._runner:
            await self._runner.cleanup()
        
        self._running = False
        logger.info("Notification server stopped")
    
    async def __aenter__(self) -> "NotificationServer":
        """Context manager 進入"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager 離開"""
        await self.stop()
