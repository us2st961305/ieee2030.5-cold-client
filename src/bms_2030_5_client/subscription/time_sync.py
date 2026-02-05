"""
Time Synchronization Client (時間同步客戶端)

IEEE 2030.5 時間資源 (/tm) 不可訂閱，必須透過輪詢進行時間同步。

Reference: IEEE Std 2030.5-2023, Clause 9.2.3
- 同步後輪詢不超過每 15 分鐘一次
- Time 資源無法訂閱

使用方式:
    time_sync = TimeSyncClient(http_client)
    await time_sync.sync()
    await time_sync.start_sync_loop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from bms_2030_5_client.models import Time

if TYPE_CHECKING:
    from bms_2030_5_client.ieee2030_5 import IEEE2030_5Client

logger = logging.getLogger(__name__)


@dataclass
class TimeSyncConfig:
    """時間同步配置"""
    
    # 同步間隔（秒）- IEEE 2030.5 規定最少 15 分鐘
    sync_interval_s: float = 900.0  # 15 minutes
    
    # 允許的時間偏差（秒）
    max_drift_s: float = 5.0
    
    # 是否自動調整本地時鐘（通常只記錄偏差）
    auto_adjust: bool = False
    
    # 重試次數
    max_retries: int = 3
    
    # 重試間隔（秒）
    retry_interval_s: float = 60.0


@dataclass
class TimeSyncResult:
    """時間同步結果"""
    server_time: int            # 伺服器時間 (Unix timestamp)
    local_time: int             # 本地時間 (Unix timestamp)
    drift_s: float              # 偏差（秒）
    synced: bool                # 是否同步成功
    adjusted: bool = False      # 是否調整了本地時鐘


class TimeSyncClient:
    """
    IEEE 2030.5 時間同步客戶端
    
    根據 IEEE 2030.5-2023 第 9.2.3 節：
    - Time 資源不可訂閱
    - 必須透過輪詢進行時間同步
    - 同步頻率不超過每 15 分鐘一次
    
    使用方式:
        time_sync = TimeSyncClient(http_client)
        
        # 單次同步
        result = await time_sync.sync()
        if result.drift_s > 5:
            logger.warning(f"Time drift: {result.drift_s}s")
        
        # 啟動同步迴圈
        await time_sync.start_sync_loop()
    """
    
    def __init__(
        self,
        http_client: "IEEE2030_5Client",
        config: Optional[TimeSyncConfig] = None,
    ):
        """
        初始化時間同步客戶端
        
        Args:
            http_client: IEEE 2030.5 HTTP 客戶端
            config: 同步配置
        """
        self.http_client = http_client
        self.config = config or TimeSyncConfig()
        
        # 同步狀態
        self._last_sync_time: Optional[float] = None
        self._last_drift_s: Optional[float] = None
        self._sync_count: int = 0
        self._error_count: int = 0
        
        # 同步任務
        self._sync_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            f"TimeSyncClient initialized, "
            f"interval={self.config.sync_interval_s}s"
        )
    
    @property
    def last_sync_time(self) -> Optional[float]:
        """取得上次同步時間"""
        return self._last_sync_time
    
    @property
    def last_drift_s(self) -> Optional[float]:
        """取得上次測量的偏差"""
        return self._last_drift_s
    
    @property
    def stats(self) -> dict:
        """取得統計資料"""
        return {
            "sync_count": self._sync_count,
            "error_count": self._error_count,
            "last_sync_time": self._last_sync_time,
            "last_drift_s": self._last_drift_s,
        }
    
    # =========================================================================
    # Synchronization (同步)
    # =========================================================================
    
    async def sync(self) -> TimeSyncResult:
        """
        執行時間同步
        
        Returns:
            TimeSyncResult 包含同步結果
        """
        logger.debug("Performing time synchronization...")
        
        local_before = int(time.time())
        
        try:
            # 取得伺服器時間
            server_time = await self.http_client.get_time()
            
            local_after = int(time.time())
            
            # 計算偏差（考慮網路延遲）
            local_mid = (local_before + local_after) / 2
            drift_s = server_time.currentTime - local_mid
            
            self._last_sync_time = time.time()
            self._last_drift_s = drift_s
            self._sync_count += 1
            
            synced = abs(drift_s) <= self.config.max_drift_s
            
            result = TimeSyncResult(
                server_time=server_time.currentTime,
                local_time=int(local_mid),
                drift_s=drift_s,
                synced=synced,
            )
            
            if synced:
                logger.debug(f"Time synchronized, drift={drift_s:.2f}s")
            else:
                logger.warning(
                    f"Time drift detected: {drift_s:.2f}s "
                    f"(threshold={self.config.max_drift_s}s)"
                )
                
                # 自動調整（通常不建議在應用層調整系統時鐘）
                if self.config.auto_adjust:
                    logger.info(f"Auto-adjusting time offset by {drift_s:.2f}s")
                    result.adjusted = True
            
            return result
        
        except Exception as e:
            logger.error(f"Time synchronization failed: {e}")
            self._error_count += 1
            
            return TimeSyncResult(
                server_time=0,
                local_time=local_before,
                drift_s=0,
                synced=False,
            )
    
    async def sync_with_retry(self) -> TimeSyncResult:
        """
        執行時間同步（含重試）
        
        Returns:
            TimeSyncResult
        """
        for attempt in range(self.config.max_retries):
            result = await self.sync()
            
            if result.synced or result.server_time > 0:
                return result
            
            if attempt < self.config.max_retries - 1:
                logger.debug(
                    f"Time sync retry {attempt + 1}/{self.config.max_retries}"
                )
                await asyncio.sleep(self.config.retry_interval_s)
        
        return result
    
    # =========================================================================
    # Sync Loop (同步迴圈)
    # =========================================================================
    
    async def start_sync_loop(self) -> None:
        """啟動時間同步迴圈"""
        if self._running:
            logger.warning("Time sync loop already running")
            return
        
        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info("Time sync loop started")
    
    async def stop_sync_loop(self) -> None:
        """停止時間同步迴圈"""
        self._running = False
        
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Time sync loop stopped")
    
    async def _sync_loop(self) -> None:
        """時間同步迴圈"""
        # 立即執行一次同步
        await self.sync_with_retry()
        
        while self._running:
            try:
                await asyncio.sleep(self.config.sync_interval_s)
                
                if self._running:
                    result = await self.sync()
                    
                    # 偏差過大時記錄警告
                    if not result.synced and result.server_time > 0:
                        logger.warning(
                            f"Significant time drift: {result.drift_s:.2f}s"
                        )
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Time sync loop error: {e}")
                await asyncio.sleep(self.config.retry_interval_s)
    
    # =========================================================================
    # Utilities (工具函數)
    # =========================================================================
    
    def get_adjusted_time(self) -> int:
        """
        取得調整後的時間
        
        如果有偏差，回傳調整後的本地時間。
        
        Returns:
            調整後的 Unix 時間戳
        """
        local_time = int(time.time())
        
        if self._last_drift_s is not None:
            return int(local_time + self._last_drift_s)
        
        return local_time
    
    def is_control_active(
        self,
        start_time: int,
        duration: int
    ) -> bool:
        """
        檢查控制是否在有效時間內
        
        使用調整後的時間來判斷。
        
        Args:
            start_time: 控制開始時間
            duration: 控制持續時間（秒）
        
        Returns:
            是否處於活動狀態
        """
        now = self.get_adjusted_time()
        end_time = start_time + duration
        
        return start_time <= now < end_time
