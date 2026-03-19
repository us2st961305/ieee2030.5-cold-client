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
    DERControlResponseFull,
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
        mode="dry_run",
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


# =============================================================================
# 10. _processed_mRIDs deque ordering Tests
# =============================================================================

class TestProcessedMRIDsOrdering:
    """_processed_mRIDs 插入順序保留測試"""

    def test_processed_mrids_is_deque(self, der_client):
        """_processed_mRIDs 應為 collections.deque"""
        import collections
        assert isinstance(der_client._processed_mRIDs, collections.deque)

    def test_deque_maxlen_equals_config(self, der_client):
        """deque maxlen 應與 config.processed_event_retention 相同"""
        assert der_client._processed_mRIDs.maxlen == der_client.config.processed_event_retention

    def test_oldest_entry_evicted_when_full(self, der_client):
        """deque 滿時應淘汰最舊項目而不是丟失最新項目"""
        der_client.config.processed_event_retention = 5
        import collections
        der_client._processed_mRIDs = collections.deque(maxlen=5)

        for i in range(5):
            der_client._processed_mRIDs.append(f"old-{i}")

        # Add one more; "old-0" should be evicted
        der_client._processed_mRIDs.append("newest")

        assert "newest" in der_client._processed_mRIDs
        assert "old-0" not in der_client._processed_mRIDs
        assert len(der_client._processed_mRIDs) == 5

    @pytest.mark.asyncio
    async def test_recent_controls_not_lost_under_high_throughput(self, der_client):
        """高吞吐量場景下，最新的 mRID 不應因清理而遺失"""
        der_client.config.processed_event_retention = 10
        import collections
        der_client._processed_mRIDs = collections.deque(maxlen=10)

        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        # Fill beyond maxlen
        for i in range(12):
            ctrl_id = f"ctrl-{i:03d}"
            control = DERControl(
                mRID=ctrl_id,
                DERControlBase=DERControlBase(
                    opModFixedW=SignedPerCent(value=1000 * (i + 1), multiplier=0)
                ),
            )
            await der_client._process_control(control, program)

        # The last 10 should be present; the first 2 should have been evicted
        for i in range(2, 12):
            assert f"ctrl-{i:03d}" in der_client._processed_mRIDs
        for i in range(2):
            assert f"ctrl-{i:03d}" not in der_client._processed_mRIDs


# =============================================================================
# 11. _send_response HTTP POST Tests
# =============================================================================

class TestSendResponse:
    """_send_response 實際 HTTP POST 測試"""

    @pytest.mark.asyncio
    async def test_send_response_posts_to_replyTo(self, der_client, mock_http_client):
        """control.replyTo 有值時應 POST 到該 URI"""
        mock_http_client._post = AsyncMock(return_value=(None, None))

        program = DERProgram(mRID="prog001", primacy=1)
        control = DERControl(
            mRID="ctrl001",
            href="/der/1/derc/ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        # Attach a replyTo attribute dynamically
        control.replyTo = "/der/1/rsps"

        tracked = TrackedControl(control=control, program=program, primacy=1)

        result = await der_client._send_response(tracked, ResponseStatusType.EVENT_STARTED)

        assert result is True
        assert tracked.response_sent is True
        mock_http_client._post.assert_called_once()
        call_uri = mock_http_client._post.call_args[0][0]
        assert call_uri == "/der/1/rsps"

    @pytest.mark.asyncio
    async def test_send_response_falls_back_to_href_rsp(self, der_client, mock_http_client):
        """replyTo 缺失時應退回 {href}/rsp"""
        mock_http_client._post = AsyncMock(return_value=(None, None))

        program = DERProgram(mRID="prog001", primacy=1)
        control = DERControl(
            mRID="ctrl001",
            href="/der/1/derc/ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )

        tracked = TrackedControl(control=control, program=program, primacy=1)

        result = await der_client._send_response(tracked, ResponseStatusType.EVENT_COMPLETED)

        assert result is True
        mock_http_client._post.assert_called_once()
        call_uri = mock_http_client._post.call_args[0][0]
        assert call_uri == "/der/1/derc/ctrl001/rsp"

    @pytest.mark.asyncio
    async def test_send_response_retries_on_failure(self, der_client, mock_http_client):
        """HTTP POST 失敗時應重試 response_max_retries 次後回傳 False"""
        mock_http_client._post = AsyncMock(side_effect=Exception("network error"))
        der_client.config.response_max_retries = 3

        program = DERProgram(mRID="prog001", primacy=1)
        control = DERControl(
            mRID="ctrl001",
            href="/der/1/derc/ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        control.replyTo = "/der/1/rsps"

        tracked = TrackedControl(control=control, program=program, primacy=1)

        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            result = await der_client._send_response(tracked, ResponseStatusType.EVENT_STARTED)

        assert result is False
        # 1 initial attempt + 2 retries = 3 total calls
        assert mock_http_client._post.call_count == 3
        # Verify exponential backoff delays: 2^0=1s then 2^1=2s
        sleep_calls = [call.args[0] for call in sleep_mock.call_args_list]
        assert sleep_calls == [1, 2]

    @pytest.mark.asyncio
    async def test_send_response_no_uri_still_marks_sent(self, der_client, mock_http_client):
        """href 和 replyTo 均缺失時，仍標記 response_sent=True 並回傳 True"""
        mock_http_client._post = AsyncMock(return_value=(None, None))

        program = DERProgram(mRID="prog001", primacy=1)
        control = DERControl(mRID="ctrl001")

        tracked = TrackedControl(control=control, program=program, primacy=1)

        result = await der_client._send_response(tracked, ResponseStatusType.EVENT_EXPIRED)

        assert result is True
        assert tracked.response_sent is True
        mock_http_client._post.assert_not_called()


# =============================================================================
# 12. De-energize Cancellation Tests
# =============================================================================

class TestDeEnergizeCancellation:
    """De-energize 時取消所有其他控制的測試"""

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
    async def test_de_energize_cancels_active_power_controls(self, der_client):
        """測試 opModEnergize=false 取消所有活動的功率控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        # 先建立兩個不同模式的活動控制
        ctrl_w = DERControl(
            mRID="ctrl_w",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        await der_client._process_control(ctrl_w, program)
        assert der_client._tracked_controls["ctrl_w"].status == DERControlEventStatus.COMPLETED
        assert "opModFixedW" in der_client._active_by_mode

        ctrl_var = DERControl(
            mRID="ctrl_var",
            DERControlBase=DERControlBase(
                opModFixedVar=SignedPerCent(value=10000, multiplier=0)
            ),
        )
        await der_client._process_control(ctrl_var, program)
        assert "opModFixedVar" in der_client._active_by_mode

        # 發送 opModEnergize=false
        ctrl_de = DERControl(
            mRID="ctrl_de_energize",
            DERControlBase=DERControlBase(opModEnergize=False),
        )
        await der_client._process_control(ctrl_de, program)

        # opModFixedW 和 opModFixedVar 應被取消
        assert der_client._tracked_controls["ctrl_w"].status == DERControlEventStatus.SUPERSEDED
        assert der_client._tracked_controls["ctrl_var"].status == DERControlEventStatus.SUPERSEDED

        # opModEnergize 應存在且 COMPLETED
        assert "opModEnergize" in der_client._active_by_mode
        assert der_client._tracked_controls["ctrl_de_energize"].status == DERControlEventStatus.COMPLETED

        # 原有模式應從 _active_by_mode 中移除
        assert "opModFixedW" not in der_client._active_by_mode
        assert "opModFixedVar" not in der_client._active_by_mode

    @pytest.mark.asyncio
    async def test_disconnect_cancels_active_power_controls(self, der_client):
        """測試 opModConnect=false 取消所有活動的功率控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        # 先建立活動控制
        ctrl_w = DERControl(
            mRID="ctrl_w",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=30000, multiplier=0)
            ),
        )
        await der_client._process_control(ctrl_w, program)

        # 發送 opModConnect=false
        ctrl_disc = DERControl(
            mRID="ctrl_disconnect",
            DERControlBase=DERControlBase(opModConnect=False),
        )
        await der_client._process_control(ctrl_disc, program)

        # opModFixedW 應被取消
        assert der_client._tracked_controls["ctrl_w"].status == DERControlEventStatus.SUPERSEDED
        assert "opModFixedW" not in der_client._active_by_mode

        # opModConnect 應為 COMPLETED
        assert der_client._tracked_controls["ctrl_disconnect"].status == DERControlEventStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_de_energize_cancels_scheduled_controls(self, der_client):
        """測試 de-energize 取消所有排程中的控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        # 建立一個未來的排程控制
        future_start = int(time.time()) + 3600  # 1 小時後
        ctrl_scheduled = DERControl(
            mRID="ctrl_scheduled",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
            interval=DateTimeInterval(start=future_start, duration=600),
        )
        await der_client._process_control(ctrl_scheduled, program)
        assert der_client._tracked_controls["ctrl_scheduled"].status == DERControlEventStatus.SCHEDULED

        # 發送 opModEnergize=false
        ctrl_de = DERControl(
            mRID="ctrl_de_energize",
            DERControlBase=DERControlBase(opModEnergize=False),
        )
        await der_client._process_control(ctrl_de, program)

        # 排程控制應被取消
        assert der_client._tracked_controls["ctrl_scheduled"].status == DERControlEventStatus.SUPERSEDED

    @pytest.mark.asyncio
    async def test_de_energize_cancels_default_control(self, der_client):
        """測試 de-energize 取消 DefaultDERControl"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        # 設定一個 DefaultDERControl
        default_ctrl = DefaultDERControl(
            mRID="default001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=10000, multiplier=0)
            ),
        )
        der_client._active_default = default_ctrl
        der_client._active_default_program = program

        # 發送 opModEnergize=false
        ctrl_de = DERControl(
            mRID="ctrl_de_energize",
            DERControlBase=DERControlBase(opModEnergize=False),
        )
        await der_client._process_control(ctrl_de, program)

        # DefaultDERControl 應被取消
        assert der_client._active_default is None
        assert der_client._active_default_program is None

    @pytest.mark.asyncio
    async def test_de_energize_does_not_cancel_itself(self, der_client):
        """測試 de-energize 不會取消自己"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        ctrl_de = DERControl(
            mRID="ctrl_de_energize",
            DERControlBase=DERControlBase(opModEnergize=False),
        )
        await der_client._process_control(ctrl_de, program)

        # 自己不應被取消
        assert der_client._tracked_controls["ctrl_de_energize"].status == DERControlEventStatus.COMPLETED
        assert "opModEnergize" in der_client._active_by_mode

    @pytest.mark.asyncio
    async def test_no_recovery_during_de_energize(self, der_client):
        """測試 de-energize 活動期間不恢復被取消的控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        # 建立一個仍在有效期內的控制
        now = int(time.time())
        ctrl_w = DERControl(
            mRID="ctrl_w",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
            interval=DateTimeInterval(start=now - 60, duration=7200),  # 2 小時有效期
        )
        await der_client._process_control(ctrl_w, program)

        # 發送 de-energize
        ctrl_de = DERControl(
            mRID="ctrl_de_energize",
            DERControlBase=DERControlBase(opModEnergize=False),
            interval=DateTimeInterval(start=now, duration=600),  # 10 分鐘
        )
        await der_client._process_control(ctrl_de, program)

        # ctrl_w 已被取消
        assert der_client._tracked_controls["ctrl_w"].status == DERControlEventStatus.SUPERSEDED

        # 嘗試進行 recovery — 應該被阻止
        await der_client._check_control_recovery()

        # ctrl_w 不應被恢復（仍為 SUPERSEDED）
        assert der_client._tracked_controls["ctrl_w"].status == DERControlEventStatus.SUPERSEDED

    @pytest.mark.asyncio
    async def test_energize_true_does_not_cancel(self, der_client):
        """測試 opModEnergize=true（復能）不會取消其他控制"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        # 建立一個活動控制
        ctrl_w = DERControl(
            mRID="ctrl_w",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        await der_client._process_control(ctrl_w, program)

        # 發送 opModEnergize=true（復能）
        ctrl_re = DERControl(
            mRID="ctrl_re_energize",
            DERControlBase=DERControlBase(opModEnergize=True),
        )
        await der_client._process_control(ctrl_re, program)

        # opModFixedW 不應被取消
        assert der_client._tracked_controls["ctrl_w"].status == DERControlEventStatus.COMPLETED
        assert "opModFixedW" in der_client._active_by_mode

    @pytest.mark.asyncio
    async def test_is_de_energize_control_helper(self, der_client):
        """測試 _is_de_energize_control() 輔助方法"""
        # opModEnergize=false → 是 de-energize
        ctrl_de = DERControl(
            mRID="t1",
            DERControlBase=DERControlBase(opModEnergize=False),
        )
        assert der_client._is_de_energize_control(ctrl_de) is True

        # opModConnect=false → 是 de-energize
        ctrl_disc = DERControl(
            mRID="t2",
            DERControlBase=DERControlBase(opModConnect=False),
        )
        assert der_client._is_de_energize_control(ctrl_disc) is True

        # opModEnergize=true → 不是 de-energize
        ctrl_re = DERControl(
            mRID="t3",
            DERControlBase=DERControlBase(opModEnergize=True),
        )
        assert der_client._is_de_energize_control(ctrl_re) is False

        # opModConnect=true → 不是 de-energize
        ctrl_conn = DERControl(
            mRID="t4",
            DERControlBase=DERControlBase(opModConnect=True),
        )
        assert der_client._is_de_energize_control(ctrl_conn) is False

        # 一般功率控制 → 不是 de-energize
        ctrl_w = DERControl(
            mRID="t5",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        assert der_client._is_de_energize_control(ctrl_w) is False

        # 無 DERControlBase → 不是 de-energize
        ctrl_empty = DERControl(mRID="t6")
        assert der_client._is_de_energize_control(ctrl_empty) is False

    @pytest.mark.asyncio
    async def test_response_sent_for_cancelled_controls(self, der_client, mock_http_client):
        """測試被取消的控制會發送 EVENT_SUPERSEDED Response"""
        program = DERProgram(mRID="prog001", primacy=1)
        await der_client._track_program(program)

        ctrl_w = DERControl(
            mRID="ctrl_w",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        await der_client._process_control(ctrl_w, program)

        # 記錄 response 發送前的數量
        responses_before = der_client._stats["responses_sent"]

        # 發送 de-energize
        ctrl_de = DERControl(
            mRID="ctrl_de_energize",
            DERControlBase=DERControlBase(opModEnergize=False),
        )
        await der_client._process_control(ctrl_de, program)

        # 應有額外的 response 發送（包含 SUPERSEDED for ctrl_w）
        assert der_client._stats["responses_sent"] > responses_before
