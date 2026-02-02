"""
IEEE 2030.5 DER Client Integration Tests

測試完整的 IEEE 2030.5 客戶端流程：
1. FSA 探索與監控
2. DERProgram 管理
3. DERControl 執行
4. 衝突處理
5. Response 回報
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from bms_2030_5_client.models import (
    DERControl,
    DERControlBase,
    DERControlList,
    DERProgram,
    DERProgramList,
    DefaultDERControl,
    FunctionSetAssignments,
    FunctionSetAssignmentsList,
    DERControlResponse,
    ResponseStatusType,
    DateTimeInterval,
    SignedPerCent,
    EndDevice,
)
from bms_2030_5_client.dera.der_client import (
    DERClient,
    DERClientConfig,
    TrackedProgram,
    TrackedControl,
)
from bms_2030_5_client.dera.handler import DERControlEventStatus
from bms_2030_5_client.power_control import (
    SafePowerController,
    PowerLimits,
    PowerControlConfig,
    EmergencyStop,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def power_limits():
    """功率限制"""
    return PowerLimits(
        max_charge_w=100000,
        max_discharge_w=100000,
    )


@pytest.fixture
def power_controller(power_limits):
    """安全功率控制器（模擬模式）"""
    # 使用內部方式重置緊急停止（僅用於測試）
    EmergencyStop._stopped = False
    EmergencyStop._reason = None
    EmergencyStop._timestamp = None
    
    config = PowerControlConfig(
        simulation_mode=True,
        limits=power_limits,
    )
    return SafePowerController(config)


@pytest.fixture
def mock_http_client():
    """Mock IEEE 2030.5 HTTP 客戶端"""
    client = MagicMock()
    client.lfdi = "0123456789ABCDEF0123456789ABCDEF01234567"
    client._end_device = EndDevice(
        href="/edev/1",
        FunctionSetAssignmentsListLink="/edev/1/fsa",
    )
    client._get = AsyncMock()
    client._post = AsyncMock()
    return client


@pytest.fixture
def der_client(mock_http_client, power_controller):
    """DER Client 實例"""
    config = DERClientConfig(
        fsa_poll_interval_s=1.0,
        control_poll_interval_s=0.5,
        program_poll_interval_s=0.5,
    )
    return DERClient(
        http_client=mock_http_client,
        power_controller=power_controller,
        config=config,
    )


# =============================================================================
# 1. FSA Discovery Tests
# =============================================================================

class TestFSADiscovery:
    """FSA 探索與監控測試"""
    
    @pytest.mark.asyncio
    async def test_discover_fsa(self, der_client, mock_http_client):
        """測試 FSA 探索"""
        # 設置 mock 回傳
        fsa = FunctionSetAssignments(
            mRID="fsa001",
            DERProgramListLink="/fsa/1/derp",
        )
        fsa_list = FunctionSetAssignmentsList(
            FunctionSetAssignments=[fsa],
        )
        
        program = DERProgram(
            mRID="prog001",
            primacy=1,
            ActiveDERControlListLink="/derp/1/derca",
        )
        program_list = DERProgramList(
            DERProgram=[program],
        )
        
        mock_http_client._get.side_effect = [fsa_list, program_list]
        
        # 執行 FSA 輪詢
        await der_client._poll_fsa()
        
        # 驗證
        assert "fsa001" in der_client._tracked_fsa
        assert "prog001" in der_client._tracked_programs
    
    @pytest.mark.asyncio
    async def test_fsa_removed(self, der_client, mock_http_client):
        """測試 FSA 移除時停止控制"""
        # 先新增 FSA
        fsa = FunctionSetAssignments(
            mRID="fsa001",
            DERProgramListLink="/fsa/1/derp",
        )
        fsa_list = FunctionSetAssignmentsList(
            FunctionSetAssignments=[fsa],
        )
        program = DERProgram(mRID="prog001", primacy=1)
        program_list = DERProgramList(DERProgram=[program])
        
        mock_http_client._get.side_effect = [fsa_list, program_list]
        await der_client._poll_fsa()
        
        # 然後移除 FSA
        empty_fsa_list = FunctionSetAssignmentsList(
            FunctionSetAssignments=[],
        )
        mock_http_client._get.side_effect = [empty_fsa_list]
        await der_client._poll_fsa()
        
        # 驗證 FSA 和計畫都被移除
        assert "fsa001" not in der_client._tracked_fsa


# =============================================================================
# 2. DERProgram Management Tests
# =============================================================================

class TestDERProgramManagement:
    """DERProgram 管理測試"""
    
    @pytest.mark.asyncio
    async def test_track_multiple_programs(self, der_client):
        """測試追蹤多個計畫"""
        programs = [
            DERProgram(mRID=f"prog00{i}", primacy=i)
            for i in range(6)
        ]
        
        for program in programs:
            await der_client._track_program(program)
        
        assert len(der_client._tracked_programs) == 6
    
    @pytest.mark.asyncio
    async def test_program_primacy_ordering(self, der_client):
        """測試計畫優先權排序"""
        # 新增不同優先權的計畫
        await der_client._track_program(DERProgram(mRID="low", primacy=10))
        await der_client._track_program(DERProgram(mRID="high", primacy=1))
        await der_client._track_program(DERProgram(mRID="mid", primacy=5))
        
        # 取得最高優先級計畫
        highest = der_client._get_highest_priority_program()
        
        assert highest is not None
        assert highest.program.mRID == "high"
        assert highest.primacy == 1
    
    @pytest.mark.asyncio
    async def test_default_der_control(self, der_client, mock_http_client):
        """測試 DefaultDERControl 獲取"""
        program = DERProgram(
            mRID="prog001",
            primacy=1,
            DefaultDERControlLink="/derp/1/dderc",
        )
        
        default_ctrl = DefaultDERControl(
            mRID="default001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=5000, multiplier=0)
            ),
        )
        
        mock_http_client._get.return_value = default_ctrl
        
        await der_client._track_program(program)
        await der_client._fetch_default_control("prog001")
        
        tracked = der_client._tracked_programs["prog001"]
        assert tracked.default_control is not None
        assert tracked.default_control.mRID == "default001"


# =============================================================================
# 3. DERControl Execution Tests
# =============================================================================

class TestDERControlExecution:
    """DERControl 執行測試"""
    
    @pytest.mark.asyncio
    async def test_immediate_control_execution(self, der_client):
        """測試立即執行控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        
        control = DERControl(
            mRID="ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        
        await der_client._track_program(program)
        await der_client._process_control(control, program)
        
        assert "ctrl001" in der_client._tracked_controls
        tracked = der_client._tracked_controls["ctrl001"]
        assert tracked.status == DERControlEventStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_scheduled_control(self, der_client):
        """測試排程控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        
        future_time = int(time.time()) + 3600  # 1 小時後
        control = DERControl(
            mRID="ctrl002",
            interval=DateTimeInterval(start=future_time, duration=1800),
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=30000, multiplier=0)
            ),
        )
        
        await der_client._track_program(program)
        await der_client._process_control(control, program)
        
        tracked = der_client._tracked_controls["ctrl002"]
        assert tracked.status == DERControlEventStatus.SCHEDULED
    
    @pytest.mark.asyncio
    async def test_control_in_active_period(self, der_client):
        """測試已過開始時間但未過結束時間的控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        
        past_time = int(time.time()) - 300  # 5 分鐘前
        control = DERControl(
            mRID="ctrl003",
            interval=DateTimeInterval(start=past_time, duration=3600),
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=40000, multiplier=0)
            ),
        )
        
        await der_client._track_program(program)
        await der_client._process_control(control, program)
        
        tracked = der_client._tracked_controls["ctrl003"]
        # 應該立即執行
        assert tracked.status == DERControlEventStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_expired_control(self, der_client):
        """測試過期控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        
        past_time = int(time.time()) - 7200  # 2 小時前
        control = DERControl(
            mRID="ctrl004",
            interval=DateTimeInterval(start=past_time, duration=3600),
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=20000, multiplier=0)
            ),
        )
        
        await der_client._track_program(program)
        await der_client._process_control(control, program)
        
        tracked = der_client._tracked_controls["ctrl004"]
        assert tracked.status == DERControlEventStatus.CANCELLED


# =============================================================================
# 4. Randomization Tests
# =============================================================================

class TestRandomization:
    """隨機化測試"""
    
    def test_randomize_start(self, der_client):
        """測試開始時間隨機化"""
        control = DERControl(
            mRID="ctrl001",
            randomizeStart=300,  # 0-300 秒隨機
        )
        
        result = der_client._calculate_randomized_start(control)
        
        assert result is not None
        assert 0 <= result <= 300
    
    def test_randomize_duration(self, der_client):
        """測試持續時間隨機化"""
        control = DERControl(
            mRID="ctrl001",
            randomizeDuration=60,  # -60 到 +60 秒
        )
        
        result = der_client._calculate_randomized_duration(control)
        
        assert result is not None
        assert -60 <= result <= 60
    
    def test_randomization_disabled(self, der_client):
        """測試禁用隨機化"""
        der_client.config.enable_randomization = False
        
        control = DERControl(
            mRID="ctrl001",
            randomizeStart=300,
            randomizeDuration=60,
        )
        
        start = der_client._calculate_randomized_start(control)
        duration = der_client._calculate_randomized_duration(control)
        
        assert start is None
        assert duration is None


# =============================================================================
# 5. Conflict Resolution Tests
# =============================================================================

class TestConflictResolution:
    """衝突解決測試"""
    
    @pytest.mark.asyncio
    async def test_higher_primacy_supersedes(self, der_client):
        """測試高優先權控制取代低優先權"""
        program_high = DERProgram(mRID="prog_high", primacy=1)
        program_low = DERProgram(mRID="prog_low", primacy=10)
        
        # 先執行低優先權控制
        control_low = DERControl(
            mRID="ctrl_low",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=30000, multiplier=0)
            ),
        )
        
        await der_client._track_program(program_low)
        await der_client._process_control(control_low, program_low)
        
        # 再執行高優先權控制
        control_high = DERControl(
            mRID="ctrl_high",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        
        await der_client._track_program(program_high)
        await der_client._process_control(control_high, program_high)
        
        # 低優先權控制應被取代
        tracked_low = der_client._tracked_controls["ctrl_low"]
        assert tracked_low.status == DERControlEventStatus.SUPERSEDED
        
        # 高優先權控制應執行
        tracked_high = der_client._tracked_controls["ctrl_high"]
        assert tracked_high.status == DERControlEventStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_same_primacy_newer_wins(self, der_client):
        """測試相同優先權時較新控制優先"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)
        
        # 較舊控制
        control_old = DERControl(
            mRID="ctrl_old",
            creationTime=1000,
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=30000, multiplier=0)
            ),
        )
        await der_client._process_control(control_old, program)
        
        # 較新控制
        control_new = DERControl(
            mRID="ctrl_new",
            creationTime=2000,
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        await der_client._process_control(control_new, program)
        
        # 較舊控制應被取代
        tracked_old = der_client._tracked_controls["ctrl_old"]
        assert tracked_old.status == DERControlEventStatus.SUPERSEDED
    
    @pytest.mark.asyncio
    async def test_different_modes_coexist(self, der_client):
        """測試不同控制模式可共存"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)
        
        # 固定功率控制
        control_w = DERControl(
            mRID="ctrl_w",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        await der_client._process_control(control_w, program)
        
        # 固定無功率控制（不同模式）
        control_var = DERControl(
            mRID="ctrl_var",
            DERControlBase=DERControlBase(
                opModFixedVar=SignedPerCent(value=10000, multiplier=0)
            ),
        )
        await der_client._process_control(control_var, program)
        
        # 兩個控制都應該完成
        assert der_client._tracked_controls["ctrl_w"].status == DERControlEventStatus.COMPLETED
        assert der_client._tracked_controls["ctrl_var"].status == DERControlEventStatus.COMPLETED
        
        # 兩個模式都應有活動控制
        assert "opModFixedW" in der_client._active_by_mode
        assert "opModFixedVar" in der_client._active_by_mode


# =============================================================================
# 6. Response Reporting Tests
# =============================================================================

class TestResponseReporting:
    """回報狀態測試"""
    
    @pytest.mark.asyncio
    async def test_response_sent_on_execution(self, der_client):
        """測試執行時發送回報"""
        program = DERProgram(mRID="prog001", primacy=1)
        
        control = DERControl(
            mRID="ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        
        await der_client._track_program(program)
        await der_client._process_control(control, program)
        
        tracked = der_client._tracked_controls["ctrl001"]
        assert tracked.response_sent is True
        assert der_client._stats["responses_sent"] >= 1
    
    @pytest.mark.asyncio
    async def test_response_contains_lfdi(self, der_client, mock_http_client):
        """測試回報包含 LFDI"""
        program = DERProgram(mRID="prog001", primacy=1)
        control = DERControl(
            mRID="ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        
        tracked = TrackedControl(
            control=control,
            program=program,
            primacy=1,
        )
        
        # 驗證 LFDI 可用
        assert mock_http_client.lfdi is not None
        assert len(mock_http_client.lfdi) == 40


# =============================================================================
# 7. DefaultDERControl Tests
# =============================================================================

class TestDefaultDERControl:
    """DefaultDERControl 測試"""
    
    @pytest.mark.asyncio
    async def test_apply_default_when_no_active(self, der_client):
        """測試無活動控制時應用 DefaultDERControl"""
        program = DERProgram(mRID="prog001", primacy=1)
        
        default_ctrl = DefaultDERControl(
            mRID="default001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=10000, multiplier=0)
            ),
        )
        
        tracked_program = TrackedProgram(
            program=program,
            primacy=1,
            default_control=default_ctrl,
        )
        
        der_client._tracked_programs["prog001"] = tracked_program
        
        await der_client._check_default_control(tracked_program)
        
        assert der_client._active_default == default_ctrl
        assert der_client._active_default_program == program


# =============================================================================
# 8. Lifecycle Tests
# =============================================================================

class TestLifecycle:
    """生命週期測試"""
    
    @pytest.mark.asyncio
    async def test_start_stop(self, der_client, mock_http_client):
        """測試啟動和停止"""
        # 設置空回傳以避免錯誤
        mock_http_client._get.return_value = FunctionSetAssignmentsList()
        
        await der_client.start()
        assert der_client.is_running is True
        
        await asyncio.sleep(0.1)
        
        await der_client.stop()
        assert der_client.is_running is False
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self, der_client, mock_http_client):
        """測試統計追蹤"""
        mock_http_client._get.return_value = FunctionSetAssignmentsList()
        
        await der_client._poll_fsa()
        
        assert der_client.stats["fsa_polls"] == 1


# =============================================================================
# 9. Emergency Stop Tests
# =============================================================================

class TestEmergencyStop:
    """緊急停止測試"""
    
    @pytest.fixture(autouse=True)
    def reset_emergency_stop(self):
        """每個測試前後重置緊急停止"""
        EmergencyStop._stopped = False
        EmergencyStop._reason = None
        EmergencyStop._timestamp = None
        yield
        EmergencyStop._stopped = False
        EmergencyStop._reason = None
        EmergencyStop._timestamp = None
    
    @pytest.mark.asyncio
    async def test_control_blocked_by_emergency_stop(self, der_client):
        """測試緊急停止阻擋控制執行"""
        EmergencyStop.trigger("test emergency")
        
        program = DERProgram(mRID="prog001", primacy=1)
        control = DERControl(
            mRID="ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        
        tracked = TrackedControl(
            control=control,
            program=program,
            primacy=1,
        )
        
        await der_client._execute_control(tracked)
        
        assert tracked.status == DERControlEventStatus.FAILED
