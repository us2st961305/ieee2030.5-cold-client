"""
DER Control History Recorder - 記錄 DER 控制指令的歷史

追蹤所有 IEEE 2030.5 DER 相關資源的：
- FSA (FunctionSetAssignments) 資源
- DERProgram 資源
- DERControl 指令的接收、執行、回報

供 Web UI 完整呈現 /fsa /derp /derc 的收發資料
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Log Records
# =============================================================================

class RequestType(str, Enum):
    """HTTP 請求類型"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


@dataclass
class ResourceRequestLog:
    """資源請求/回應記錄 - 包含完整的請求與回應內容"""
    id: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 請求資訊
    request_type: RequestType = RequestType.GET
    resource_type: str = "unknown"  # "fsa", "derp", "derc", "derc_list", "response"
    uri: str = ""
    request_headers: Optional[Dict[str, str]] = None
    request_body: Optional[str] = None  # XML/JSON 內容
    
    # 回應資訊
    response_code: int = 0
    response_time_ms: float = 0
    response_body_size: int = 0
    response_headers: Optional[Dict[str, str]] = None
    response_body: Optional[str] = None  # XML/JSON 內容 (截斷至 max_body_size)
    success: bool = False
    error_message: Optional[str] = None
    
    # 資源摘要
    resource_count: int = 0  # 列表中的資源數量
    resource_summary: Optional[str] = None  # 簡短摘要
    
    def to_dict(self, include_body: bool = False) -> Dict[str, Any]:
        """
        轉換為字典供 JSON 序列化
        
        Args:
            include_body: 是否包含完整的請求/回應內容
        """
        result = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "request_type": self.request_type.value,
            "resource_type": self.resource_type,
            "uri": self.uri,
            "response_code": self.response_code,
            "response_time_ms": self.response_time_ms,
            "response_body_size": self.response_body_size,
            "success": self.success,
            "error_message": self.error_message,
            "resource_count": self.resource_count,
            "resource_summary": self.resource_summary,
        }
        
        if include_body:
            result["request_headers"] = self.request_headers
            result["request_body"] = self.request_body
            result["response_headers"] = self.response_headers
            result["response_body"] = self.response_body
        
        return result


@dataclass
class FSARecord:
    """FSA 資源記錄"""
    id: str  # mRID or href
    timestamp: datetime = field(default_factory=datetime.now)
    
    # FSA 屬性
    href: Optional[str] = None
    description: Optional[str] = None
    version: int = 0
    
    # 關聯資源
    der_program_list_link: Optional[str] = None
    program_count: int = 0
    
    # 狀態
    status: str = "active"  # active/removed
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "href": self.href,
            "description": self.description,
            "version": self.version,
            "der_program_list_link": self.der_program_list_link,
            "program_count": self.program_count,
            "status": self.status,
        }


@dataclass
class DERProgramRecord:
    """DERProgram 資源記錄"""
    id: str  # mRID
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 程式屬性
    href: Optional[str] = None
    description: Optional[str] = None
    primacy: int = 255
    version: int = 0
    
    # 關聯資源
    fsa_id: Optional[str] = None
    der_control_list_link: Optional[str] = None
    default_der_control_link: Optional[str] = None
    control_count: int = 0
    
    # 狀態
    status: str = "active"  # active/inactive/removed
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "href": self.href,
            "description": self.description,
            "primacy": self.primacy,
            "version": self.version,
            "fsa_id": self.fsa_id,
            "der_control_list_link": self.der_control_list_link,
            "default_der_control_link": self.default_der_control_link,
            "control_count": self.control_count,
            "status": self.status,
        }


@dataclass
class DERControlRecord:
    """DER 控制記錄"""
    # 基本資訊
    id: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 控制來源
    source: str = "unknown"  # "polling" / "subscription" / "program:xxx"
    program_id: Optional[str] = None
    primacy: int = 255  # 優先權
    
    # 控制內容
    control_type: str = "unknown"  # "opModFixedW" / "opModFixedVar" / etc
    power_setpoint_w: Optional[int] = None
    var_setpoint: Optional[int] = None
    
    # 時間區間
    interval_start: Optional[int] = None
    interval_duration: Optional[int] = None
    
    # 執行狀態
    status: str = "pending"  # pending/scheduled/active/completed/failed/superseded/cancelled
    executed_at: Optional[datetime] = None
    
    # 執行結果
    result_success: bool = False
    result_simulated: bool = True
    result_message: Optional[str] = None
    
    # 回報狀態
    response_sent: bool = False
    response_status: Optional[str] = None  # EVENT_STARTED/EVENT_COMPLETED/etc
    response_time: Optional[datetime] = None
    
    # 錯誤資訊
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典供 JSON 序列化"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "program_id": self.program_id,
            "primacy": self.primacy,
            "control_type": self.control_type,
            "power_setpoint_w": self.power_setpoint_w,
            "var_setpoint": self.var_setpoint,
            "interval_start": self.interval_start,
            "interval_duration": self.interval_duration,
            "status": self.status,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "result_success": self.result_success,
            "result_simulated": self.result_simulated,
            "result_message": self.result_message,
            "response_sent": self.response_sent,
            "response_status": self.response_status,
            "response_time": self.response_time.isoformat() if self.response_time else None,
            "error_message": self.error_message,
        }


class DERControlHistoryRecorder:
    """
    DER Control 歷史記錄器
    
    記錄所有 IEEE 2030.5 DER 相關的歷史，供 Web UI 顯示：
    - HTTP 請求/回應記錄 (FSA, DERProgram, DERControl)
    - FSA 資源狀態
    - DERProgram 資源狀態
    - DERControl 指令的執行歷史
    
    使用方式:
        recorder = DERControlHistoryRecorder()
        
        # 記錄 HTTP 請求
        recorder.log_request(...)
        
        # 記錄 FSA
        recorder.record_fsa(...)
        
        # 記錄 DERProgram
        recorder.record_program(...)
        
        # 記錄控制
        record = recorder.record_control_received(control, source="polling")
        
        # 更新執行結果
        recorder.update_control_executed(record.id, result)
        
        # 取得歷史
        history = recorder.get_history(limit=50)
    """
    
    _instance: Optional["DERControlHistoryRecorder"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "DERControlHistoryRecorder":
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_records: int = 200):
        """初始化記錄器"""
        if getattr(self, "_initialized", False):
            return
        
        self._max_records = max_records
        
        # DERControl 記錄
        self._records: deque[DERControlRecord] = deque(maxlen=max_records)
        self._records_by_id: Dict[str, DERControlRecord] = {}
        self._record_lock = threading.Lock()
        
        # HTTP 請求記錄
        self._request_logs: deque[ResourceRequestLog] = deque(maxlen=max_records)
        self._request_counter = 0
        
        # FSA 記錄
        self._fsa_records: Dict[str, FSARecord] = {}
        
        # DERProgram 記錄
        self._program_records: Dict[str, DERProgramRecord] = {}
        
        # 統計
        self._stats = {
            "total_received": 0,
            "total_executed": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_superseded": 0,
            "total_responses_sent": 0,
        }
        
        # HTTP 請求統計
        self._request_stats = {
            "fsa_requests": 0,
            "derp_requests": 0,
            "derc_requests": 0,
            "response_posts": 0,
            "total_errors": 0,
        }
        
        self._initialized = True
        logger.info(f"DERControlHistoryRecorder initialized (max_records={max_records})")
    
    # =========================================================================
    # HTTP Request Logging
    # =========================================================================
    
    # 最大記錄的 body 大小（bytes）
    MAX_BODY_SIZE = 10000
    
    def log_request(
        self,
        resource_type: str,
        uri: str,
        request_type: RequestType = RequestType.GET,
        request_headers: Optional[Dict[str, str]] = None,
        request_body: Optional[str] = None,
        response_code: int = 0,
        response_time_ms: float = 0,
        response_body_size: int = 0,
        response_headers: Optional[Dict[str, str]] = None,
        response_body: Optional[str] = None,
        success: bool = False,
        error_message: Optional[str] = None,
        resource_count: int = 0,
        resource_summary: Optional[str] = None,
    ) -> ResourceRequestLog:
        """
        記錄 HTTP 請求（含完整內容）
        
        Args:
            resource_type: 資源類型 (fsa, derp, derc, response, etc.)
            uri: 請求 URI
            request_type: HTTP 方法
            request_headers: 請求標頭
            request_body: 請求內容（XML/JSON）
            response_code: HTTP 回應碼
            response_time_ms: 回應時間（毫秒）
            response_body_size: 回應內容大小
            response_headers: 回應標頭
            response_body: 回應內容（XML/JSON）
            success: 是否成功
            error_message: 錯誤訊息
            resource_count: 資源數量
            resource_summary: 資源摘要
        """
        self._request_counter += 1
        
        # 截斷過長的 body
        truncated_request_body = None
        truncated_response_body = None
        
        if request_body:
            if len(request_body) > self.MAX_BODY_SIZE:
                truncated_request_body = request_body[:self.MAX_BODY_SIZE] + "\n... [截斷]"
            else:
                truncated_request_body = request_body
        
        if response_body:
            if len(response_body) > self.MAX_BODY_SIZE:
                truncated_response_body = response_body[:self.MAX_BODY_SIZE] + "\n... [截斷]"
            else:
                truncated_response_body = response_body
        
        log_entry = ResourceRequestLog(
            id=f"req-{self._request_counter}",
            request_type=request_type,
            resource_type=resource_type,
            uri=uri,
            request_headers=request_headers,
            request_body=truncated_request_body,
            response_code=response_code,
            response_time_ms=response_time_ms,
            response_body_size=response_body_size,
            response_headers=response_headers,
            response_body=truncated_response_body,
            success=success,
            error_message=error_message,
            resource_count=resource_count,
            resource_summary=resource_summary,
        )
        
        with self._record_lock:
            self._request_logs.append(log_entry)
            
            # 更新統計 (case-insensitive comparison)
            resource_type_lower = resource_type.lower() if resource_type else ""
            if resource_type_lower == "fsa":
                self._request_stats["fsa_requests"] += 1
            elif resource_type_lower in ("derp", "derp_list", "derprogram"):
                self._request_stats["derp_requests"] += 1
            elif resource_type_lower in ("derc", "derc_list", "dercontrol"):
                self._request_stats["derc_requests"] += 1
            elif resource_type_lower == "response":
                self._request_stats["response_posts"] += 1
            
            if not success:
                self._request_stats["total_errors"] += 1
        
        return log_entry
    
    def get_request_logs(self, limit: int = 50, include_body: bool = False) -> List[Dict[str, Any]]:
        """
        取得 HTTP 請求記錄（最新的在前）
        
        Args:
            limit: 最大記錄數
            include_body: 是否包含完整的請求/回應內容
        """
        with self._record_lock:
            logs = list(self._request_logs)
            logs.reverse()
            return [log.to_dict(include_body=include_body) for log in logs[:limit]]
    
    def get_request_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        """取得單個請求的完整詳情"""
        with self._record_lock:
            for log in self._request_logs:
                if log.id == request_id:
                    return log.to_dict(include_body=True)
        return None
    
    def get_request_stats(self) -> Dict[str, Any]:
        """取得 HTTP 請求統計"""
        with self._record_lock:
            return dict(self._request_stats)
    
    # =========================================================================
    # FSA Recording
    # =========================================================================
    
    def record_fsa(
        self,
        fsa_id: str,
        href: Optional[str] = None,
        description: Optional[str] = None,
        version: int = 0,
        der_program_list_link: Optional[str] = None,
        program_count: int = 0,
    ) -> FSARecord:
        """記錄或更新 FSA"""
        with self._record_lock:
            if fsa_id in self._fsa_records:
                record = self._fsa_records[fsa_id]
                record.timestamp = datetime.now()
                record.version = version
                record.program_count = program_count
                if href:
                    record.href = href
                if description:
                    record.description = description
                if der_program_list_link:
                    record.der_program_list_link = der_program_list_link
            else:
                record = FSARecord(
                    id=fsa_id,
                    href=href,
                    description=description,
                    version=version,
                    der_program_list_link=der_program_list_link,
                    program_count=program_count,
                )
                self._fsa_records[fsa_id] = record
        
        return record
    
    def remove_fsa(self, fsa_id: str) -> None:
        """標記 FSA 為已移除"""
        with self._record_lock:
            if fsa_id in self._fsa_records:
                self._fsa_records[fsa_id].status = "removed"
    
    def get_fsa_records(self) -> List[Dict[str, Any]]:
        """取得所有 FSA 記錄"""
        with self._record_lock:
            records = list(self._fsa_records.values())
            records.sort(key=lambda r: r.timestamp, reverse=True)
            return [r.to_dict() for r in records]
    
    def get_active_fsa(self) -> List[Dict[str, Any]]:
        """取得活動的 FSA"""
        with self._record_lock:
            active = [r for r in self._fsa_records.values() if r.status == "active"]
            return [r.to_dict() for r in active]
    
    # =========================================================================
    # DERProgram Recording
    # =========================================================================
    
    def record_program(
        self,
        program_id: str,
        href: Optional[str] = None,
        description: Optional[str] = None,
        primacy: int = 255,
        version: int = 0,
        fsa_id: Optional[str] = None,
        der_control_list_link: Optional[str] = None,
        default_der_control_link: Optional[str] = None,
        control_count: int = 0,
    ) -> DERProgramRecord:
        """記錄或更新 DERProgram"""
        with self._record_lock:
            if program_id in self._program_records:
                record = self._program_records[program_id]
                record.timestamp = datetime.now()
                record.version = version
                record.primacy = primacy
                record.control_count = control_count
                if href:
                    record.href = href
                if description:
                    record.description = description
                if fsa_id:
                    record.fsa_id = fsa_id
                if der_control_list_link:
                    record.der_control_list_link = der_control_list_link
                if default_der_control_link:
                    record.default_der_control_link = default_der_control_link
            else:
                record = DERProgramRecord(
                    id=program_id,
                    href=href,
                    description=description,
                    primacy=primacy,
                    version=version,
                    fsa_id=fsa_id,
                    der_control_list_link=der_control_list_link,
                    default_der_control_link=default_der_control_link,
                    control_count=control_count,
                )
                self._program_records[program_id] = record
        
        return record
    
    def remove_program(self, program_id: str) -> None:
        """標記 DERProgram 為已移除"""
        with self._record_lock:
            if program_id in self._program_records:
                self._program_records[program_id].status = "removed"
    
    def get_program_records(self) -> List[Dict[str, Any]]:
        """取得所有 DERProgram 記錄"""
        with self._record_lock:
            records = list(self._program_records.values())
            records.sort(key=lambda r: (r.primacy, r.timestamp))
            return [r.to_dict() for r in records]
    
    def get_active_programs(self) -> List[Dict[str, Any]]:
        """取得活動的 DERProgram"""
        with self._record_lock:
            active = [r for r in self._program_records.values() if r.status == "active"]
            active.sort(key=lambda r: r.primacy)
            return [r.to_dict() for r in active]
    
    # =========================================================================
    # DERControl Recording (existing methods)
    # =========================================================================
    
    def record_control_received(
        self,
        control_id: str,
        source: str = "unknown",
        program_id: Optional[str] = None,
        primacy: int = 255,
        control_type: str = "unknown",
        power_setpoint_w: Optional[int] = None,
        var_setpoint: Optional[int] = None,
        interval_start: Optional[int] = None,
        interval_duration: Optional[int] = None,
    ) -> DERControlRecord:
        """
        記錄收到新的 DERControl 指令
        
        Returns:
            DERControlRecord 記錄物件
        """
        record = DERControlRecord(
            id=control_id,
            source=source,
            program_id=program_id,
            primacy=primacy,
            control_type=control_type,
            power_setpoint_w=power_setpoint_w,
            var_setpoint=var_setpoint,
            interval_start=interval_start,
            interval_duration=interval_duration,
            status="pending",
        )
        
        with self._record_lock:
            self._records.append(record)
            self._records_by_id[control_id] = record
            self._stats["total_received"] += 1
            
            # 清理舊記錄
            self._cleanup_old_records()
        
        logger.debug(f"Recorded DERControl received: {control_id}")
        return record
    
    def update_control_status(
        self,
        control_id: str,
        status: str,
    ) -> Optional[DERControlRecord]:
        """更新控制狀態"""
        with self._record_lock:
            record = self._records_by_id.get(control_id)
            if record:
                old_status = record.status
                record.status = status
                
                # 更新統計
                if status == "active" and old_status != "active":
                    self._stats["total_executed"] += 1
                    record.executed_at = datetime.now()
                elif status == "completed":
                    self._stats["total_completed"] += 1
                elif status == "failed":
                    self._stats["total_failed"] += 1
                elif status == "superseded":
                    self._stats["total_superseded"] += 1
                
                logger.debug(f"Control {control_id} status: {old_status} -> {status}")
            return record
    
    def update_control_executed(
        self,
        control_id: str,
        success: bool,
        simulated: bool = True,
        message: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[DERControlRecord]:
        """更新控制執行結果"""
        with self._record_lock:
            record = self._records_by_id.get(control_id)
            if record:
                record.executed_at = datetime.now()
                record.result_success = success
                record.result_simulated = simulated
                record.result_message = message
                record.error_message = error
                
                if success:
                    record.status = "completed"
                    self._stats["total_completed"] += 1
                else:
                    record.status = "failed"
                    self._stats["total_failed"] += 1
                
                logger.debug(
                    f"Control {control_id} executed: "
                    f"success={success}, simulated={simulated}"
                )
            return record
    
    def update_response_sent(
        self,
        control_id: str,
        response_status: str,
    ) -> Optional[DERControlRecord]:
        """更新回報發送狀態"""
        with self._record_lock:
            record = self._records_by_id.get(control_id)
            if record:
                record.response_sent = True
                record.response_status = response_status
                record.response_time = datetime.now()
                self._stats["total_responses_sent"] += 1
                
                logger.debug(f"Control {control_id} response: {response_status}")
            return record
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        取得控制歷史（最新的在前）
        
        Args:
            limit: 最大記錄數
            
        Returns:
            控制記錄列表
        """
        with self._record_lock:
            records = list(self._records)
            records.reverse()  # 最新的在前
            return [r.to_dict() for r in records[:limit]]
    
    def get_record(self, control_id: str) -> Optional[Dict[str, Any]]:
        """取得單個控制記錄"""
        with self._record_lock:
            record = self._records_by_id.get(control_id)
            return record.to_dict() if record else None
    
    def get_stats(self) -> Dict[str, Any]:
        """取得統計資料"""
        with self._record_lock:
            return {
                **self._stats,
                "current_records": len(self._records),
                "max_records": self._max_records,
            }
    
    def get_active_controls(self) -> List[Dict[str, Any]]:
        """取得當前活動的控制"""
        with self._record_lock:
            active = [
                r for r in self._records
                if r.status in ("pending", "scheduled", "active")
            ]
            return [r.to_dict() for r in active]
    
    def get_recent_completed(self, limit: int = 10) -> List[Dict[str, Any]]:
        """取得最近完成的控制"""
        with self._record_lock:
            completed = [
                r for r in self._records
                if r.status == "completed"
            ]
            completed.reverse()
            return [r.to_dict() for r in completed[:limit]]
    
    def clear_history(self) -> None:
        """清除所有歷史記錄"""
        with self._record_lock:
            self._records.clear()
            self._records_by_id.clear()
            self._request_logs.clear()
            self._fsa_records.clear()
            self._program_records.clear()
            self._stats = {
                "total_received": 0,
                "total_executed": 0,
                "total_completed": 0,
                "total_failed": 0,
                "total_superseded": 0,
                "total_responses_sent": 0,
            }
            self._request_stats = {
                "fsa_requests": 0,
                "derp_requests": 0,
                "derc_requests": 0,
                "response_posts": 0,
                "total_errors": 0,
            }
            self._request_counter = 0
        logger.info("DER control history cleared")
    
    def get_full_summary(self) -> Dict[str, Any]:
        """取得完整摘要資料"""
        with self._record_lock:
            return {
                "control_stats": dict(self._stats),
                "request_stats": dict(self._request_stats),
                "fsa_count": len([f for f in self._fsa_records.values() if f.status == "active"]),
                "program_count": len([p for p in self._program_records.values() if p.status == "active"]),
                "control_records": len(self._records),
                "request_logs": len(self._request_logs),
            }
    
    def _cleanup_old_records(self) -> None:
        """清理舊記錄（維護 records_by_id 的大小）"""
        # deque 已經自動限制大小，只需清理 records_by_id
        if len(self._records_by_id) > self._max_records * 2:
            # 保留最新的記錄
            current_ids = {r.id for r in self._records}
            to_remove = [
                id for id in self._records_by_id
                if id not in current_ids
            ]
            for id in to_remove:
                del self._records_by_id[id]


# 全域單例實例
_der_control_history: Optional[DERControlHistoryRecorder] = None


def get_der_control_history() -> DERControlHistoryRecorder:
    """取得全域 DERControlHistoryRecorder 實例"""
    global _der_control_history
    if _der_control_history is None:
        _der_control_history = DERControlHistoryRecorder()
    return _der_control_history
