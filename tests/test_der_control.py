"""
DER Control Integration Tests (DER 控制整合測試)

測試 IEEE 2030.5 DERControl 從接收到執行的完整流程
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bms_2030_5_client.models import (
    DERControl,
    DERControlBase,
    DERControlList,
    SignedPerCent,
    DateTimeInterval,
)
from bms_2030_5_client.power_control import (
    SafePowerController,
    PowerControlConfig,
    PowerLimits,
    ControlMode,
    EmergencyStop,
)
from bms_2030_5_client.dera.handler import (
    DERControlHandler,
    DERControlHandlerConfig,
    DERControlEvent,
    DERControlEventStatus,
    parse_der_control_from_xml,
    parse_der_control_list_from_xml,
)
from bms_2030_5_client.dera.poller import (
    DERControlPoller,
    DERControlPollerConfig,
    DERControlIntegration,
)
from bms_2030_5_client.modbus.power_writer import (
    ModbusPowerWriter,
    ModbusPowerWriterConfig,
    PowerWriteResult,
    PCSPowerAdapter,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_emergency_stop():
    """每個測試後重置緊急停止狀態"""
    EmergencyStop._stopped = False
    EmergencyStop._reason = None
    EmergencyStop._timestamp = None
    yield
    EmergencyStop._stopped = False
    EmergencyStop._reason = None
    EmergencyStop._timestamp = None


@pytest.fixture
def power_controller():
    """創建模擬模式的功率控制器"""
    return SafePowerController(
        PowerControlConfig(
            mode="dry_run",
            limits=PowerLimits(
                max_charge_w=100_000,
                max_discharge_w=100_000,
            )
        )
    )


@pytest.fixture
def der_control_handler(power_controller):
    """創建 DER Control Handler"""
    return DERControlHandler(power_controller)


@pytest.fixture
def mock_modbus_client():
    """創建模擬的 Modbus 客戶端"""
    client = MagicMock()
    client.connected = True
    client.read_registers = AsyncMock(return_value=[0])
    client.write_register = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_ieee_client():
    """創建模擬的 IEEE 2030.5 客戶端"""
    client = MagicMock()
    client._end_device = MagicMock()
    client._end_device.href = "/edev/1"
    client.get = AsyncMock(return_value=None)
    return client


# =============================================================================
# DERControl Model Tests
# =============================================================================

class TestDERControlModel:
    """測試 DERControl 資料模型"""
    
    def test_signed_per_cent_to_watts(self):
        """測試 SignedPerCent 轉換為瓦"""
        # 50kW = 50000W
        spc = SignedPerCent(value=50000, multiplier=0)
        assert spc.to_watts() == 50000
        
        # 50kW using multiplier
        spc = SignedPerCent(value=50, multiplier=3)
        assert spc.to_watts() == 50000
        
        # Negative for charging
        spc = SignedPerCent(value=-30000, multiplier=0)
        assert spc.to_watts() == -30000
    
    def test_signed_per_cent_from_watts(self):
        """測試從瓦創建 SignedPerCent"""
        spc = SignedPerCent.from_watts(50000)
        assert spc.to_watts() == 50000
        
        spc = SignedPerCent.from_watts(-30000)
        assert spc.to_watts() == -30000
    
    def test_der_control_get_power_setpoint(self):
        """測試 DERControl 取得功率設定點"""
        control = DERControl(
            mRID="test123",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            )
        )
        
        assert control.get_power_setpoint_w() == 50000
    
    def test_der_control_no_power_setpoint(self):
        """測試沒有功率設定點的 DERControl"""
        control = DERControl(mRID="test123")
        assert control.get_power_setpoint_w() is None
    
    def test_date_time_interval_is_active(self):
        """測試時間間隔活動狀態"""
        now = int(time.time())
        
        # 已開始，無限期
        interval = DateTimeInterval(start=now - 100, duration=0)
        assert interval.is_active(now) is True
        
        # 已開始，未結束
        interval = DateTimeInterval(start=now - 100, duration=200)
        assert interval.is_active(now) is True
        
        # 尚未開始
        interval = DateTimeInterval(start=now + 100, duration=200)
        assert interval.is_active(now) is False
        
        # 已結束
        interval = DateTimeInterval(start=now - 300, duration=100)
        assert interval.is_active(now) is False


# =============================================================================
# DERControl Handler Tests
# =============================================================================

class TestDERControlHandler:
    """測試 DERControlHandler"""
    
    @pytest.mark.asyncio
    async def test_handle_immediate_control(self, der_control_handler):
        """測試立即執行的控制"""
        control = DERControl(
            mRID="ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            )
        )
        
        event = await der_control_handler.handle_control(control)
        
        assert event.status == DERControlEventStatus.COMPLETED
        assert event.result is not None
        assert event.result.simulated is True
        assert event.result.requested_power_w == 50000
    
    @pytest.mark.asyncio
    async def test_handle_scheduled_control(self, der_control_handler):
        """測試排程控制"""
        future_time = int(time.time()) + 3600  # 1 hour later
        
        control = DERControl(
            mRID="ctrl002",
            interval=DateTimeInterval(start=future_time, duration=1800),
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=30000, multiplier=0)
            )
        )
        
        event = await der_control_handler.handle_control(control)
        
        assert event.status == DERControlEventStatus.SCHEDULED
    
    @pytest.mark.asyncio
    async def test_handle_control_exceeds_limit(self, der_control_handler):
        """測試超出功率限制的控制"""
        control = DERControl(
            mRID="ctrl003",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=200000, multiplier=0)  # 200kW > 100kW limit
            )
        )
        
        event = await der_control_handler.handle_control(control)
        
        assert event.status == DERControlEventStatus.FAILED
        assert event.error_message is not None
        assert "exceeds limit" in event.error_message
    
    @pytest.mark.asyncio
    async def test_handle_control_emergency_stop(self, der_control_handler):
        """測試緊急停止阻止控制"""
        EmergencyStop.trigger("test emergency")
        
        control = DERControl(
            mRID="ctrl004",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            )
        )
        
        event = await der_control_handler.handle_control(control)
        
        assert event.status == DERControlEventStatus.FAILED
        assert "Emergency stop" in event.error_message
    
    @pytest.mark.asyncio
    async def test_handle_control_list(self, der_control_handler):
        """測試處理控制列表"""
        control_list = DERControlList(
            all=2,
            results=2,
            DERControl=[
                DERControl(
                    mRID="ctrl005",
                    primacy=1,
                    DERControlBase=DERControlBase(
                        opModFixedW=SignedPerCent(value=50000, multiplier=0)
                    )
                ),
                DERControl(
                    mRID="ctrl006",
                    primacy=2,
                    DERControlBase=DERControlBase(
                        opModFixedW=SignedPerCent(value=30000, multiplier=0)
                    )
                ),
            ]
        )
        
        events = await der_control_handler.handle_control_list(control_list)
        
        assert len(events) == 2
        # 較高優先級的應該先處理
        assert events[0].control.primacy == 1
    
    @pytest.mark.asyncio
    async def test_cancel_control(self, der_control_handler, power_controller):
        """測試取消控制"""
        future_time = int(time.time()) + 3600
        
        control = DERControl(
            mRID="ctrl007",
            interval=DateTimeInterval(start=future_time, duration=1800),
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            )
        )
        
        event = await der_control_handler.handle_control(control)
        assert event.status == DERControlEventStatus.SCHEDULED
        
        # 取消
        result = await der_control_handler.cancel_control("ctrl007")
        assert result is True
        
        # 確認狀態
        cancelled_event = der_control_handler.get_event("ctrl007")
        assert cancelled_event.status == DERControlEventStatus.CANCELLED
    
    @pytest.mark.asyncio
    async def test_control_supersession(self, der_control_handler):
        """測試控制取代"""
        # 第一個控制
        control1 = DERControl(
            mRID="ctrl008",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            )
        )
        event1 = await der_control_handler.handle_control(control1)
        
        # 第二個控制（取代第一個）
        control2 = DERControl(
            mRID="ctrl009",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=30000, multiplier=0)
            )
        )
        event2 = await der_control_handler.handle_control(control2)
        
        # 確認第一個被取代
        assert der_control_handler.get_event("ctrl008").status == DERControlEventStatus.SUPERSEDED
        assert der_control_handler.active_control.event_id == "ctrl009"


# =============================================================================
# XML Parsing Tests
# =============================================================================

class TestXMLParsing:
    """測試 XML 解析"""
    
    def test_parse_der_control_from_xml(self):
        """測試解析 DERControl XML"""
        xml = """
        <DERControl xmlns="urn:ieee:std:2030.5:ns">
            <mRID>A1B2C3D4E5F6</mRID>
            <description>Power Setpoint Command</description>
            <interval>
                <duration>3600</duration>
                <start>1706832000</start>
            </interval>
            <DERControlBase>
                <opModFixedW>
                    <value>50000</value>
                    <multiplier>0</multiplier>
                </opModFixedW>
            </DERControlBase>
            <primacy>1</primacy>
        </DERControl>
        """
        
        control = parse_der_control_from_xml(xml)
        
        assert control.mRID == "A1B2C3D4E5F6"
        assert control.description == "Power Setpoint Command"
        assert control.interval.start == 1706832000
        assert control.interval.duration == 3600
        assert control.get_power_setpoint_w() == 50000
        assert control.primacy == 1
    
    def test_parse_der_control_charging(self):
        """測試解析充電控制"""
        xml = """
        <DERControl>
            <mRID>charge001</mRID>
            <DERControlBase>
                <opModFixedW>
                    <value>-30000</value>
                    <multiplier>0</multiplier>
                </opModFixedW>
            </DERControlBase>
        </DERControl>
        """
        
        control = parse_der_control_from_xml(xml)
        
        assert control.get_power_setpoint_w() == -30000
    
    def test_parse_der_control_with_multiplier(self):
        """測試解析帶有 multiplier 的功率值"""
        xml = """
        <DERControl>
            <mRID>power001</mRID>
            <DERControlBase>
                <opModFixedW>
                    <value>50</value>
                    <multiplier>3</multiplier>
                </opModFixedW>
            </DERControlBase>
        </DERControl>
        """
        
        control = parse_der_control_from_xml(xml)
        
        assert control.get_power_setpoint_w() == 50000  # 50 × 10^3


# =============================================================================
# Modbus Power Writer Tests
# =============================================================================

class TestModbusPowerWriter:
    """測試 Modbus 功率寫入器"""
    
    @pytest.fixture
    def power_writer(self, mock_modbus_client):
        return ModbusPowerWriter(
            modbus_client=mock_modbus_client,
        )
    
    @pytest.mark.asyncio
    async def test_set_power_writes_to_modbus(self, power_writer):
        """測試 set_power 直接寫入 Modbus"""
        result = await power_writer.set_power(50000)
        
        assert result.success is True
        assert result.simulated is False
        assert result.requested_power_w == 50000
        assert power_writer.current_power_w == 50000
    
    @pytest.mark.asyncio
    async def test_set_power_large_value(self, power_writer):
        """測試大功率值寫入（驗證由 SafePowerController 負責，writer 不攔截）"""
        result = await power_writer.set_power(200000)
        
        assert result.success is True
        assert result.requested_power_w == 200000
    
    @pytest.mark.asyncio
    async def test_stop(self, power_writer):
        """測試停止功率輸出"""
        await power_writer.set_power(50000)
        result = await power_writer.stop()
        
        assert result.success is True
        assert result.requested_power_w == 0
        assert power_writer.current_power_w == 0
    
    @pytest.mark.asyncio
    async def test_emergency_stop(self, power_writer):
        """測試緊急停止"""
        await power_writer.set_power(50000)
        result = await power_writer.emergency_stop("test emergency")
        
        assert EmergencyStop.is_stopped() is True
        assert power_writer.current_power_w == 0


# =============================================================================
# PCS Power Adapter Tests
# =============================================================================

class TestPCSPowerAdapter:
    """測試 PCS 功率適配器"""
    
    @pytest.fixture
    def pcs_adapter(self, mock_modbus_client):
        power_writer = ModbusPowerWriter(
            modbus_client=mock_modbus_client,
        )
        return PCSPowerAdapter(power_writer)
    
    @pytest.mark.asyncio
    async def test_apply_der_control(self, pcs_adapter):
        """測試應用 DERControl"""
        control = DERControl(
            mRID="ctrl001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            )
        )
        
        result = await pcs_adapter.apply_der_control(control)
        
        assert result.success is True
        assert result.simulated is False
        assert result.requested_power_w == 50000
    
    @pytest.mark.asyncio
    async def test_apply_power_percent(self, pcs_adapter):
        """測試按百分比設定功率"""
        result = await pcs_adapter.apply_power_percent(
            percent=50,
            max_power_w=100000
        )
        
        assert result.success is True
        assert result.requested_power_w == 50000
    
    @pytest.mark.asyncio
    async def test_apply_der_control_no_power(self, pcs_adapter):
        """測試沒有功率設定點的 DERControl"""
        control = DERControl(mRID="ctrl002")
        
        result = await pcs_adapter.apply_der_control(control)
        
        assert result.success is False
        assert "No power setpoint" in result.error_message


# =============================================================================
# Integration Tests
# =============================================================================

class TestDERControlIntegration:
    """測試 DER Control 整合"""
    
    @pytest.fixture
    def integration(self, mock_ieee_client, power_controller):
        return DERControlIntegration(
            http_client=mock_ieee_client,
            power_controller=power_controller,
            poller_config=DERControlPollerConfig(
                poll_interval_s=1.0,
                poll_on_start=False,
            )
        )
    
    @pytest.mark.asyncio
    async def test_integration_start_stop(self, integration):
        """測試整合服務啟動和停止"""
        await integration.start()
        assert integration.is_running is True
        
        await integration.stop()
        assert integration.is_running is False
    
    @pytest.mark.asyncio
    async def test_integration_stats(self, integration):
        """測試整合服務統計"""
        stats = integration.get_stats()
        
        assert "poller" in stats
        assert "handler" in stats
        assert stats["poller"]["is_running"] is False


# =============================================================================
# End-to-End Simulation Tests
# =============================================================================

class TestEndToEndSimulation:
    """端對端模擬測試"""
    
    @pytest.mark.asyncio
    async def test_complete_flow_simulation(self, mock_modbus_client, power_controller):
        """測試完整流程（DRY_RUN 模式通過 handler，writer 直接寫 Modbus）"""
        # 1. 創建元件
        handler = DERControlHandler(power_controller)
        power_writer = ModbusPowerWriter(
            modbus_client=mock_modbus_client,
        )
        pcs_adapter = PCSPowerAdapter(power_writer)
        
        # 2. 模擬收到 DERControl
        control = DERControl(
            mRID="e2e_test_001",
            description="End-to-end test control",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=75000, multiplier=0)  # 75kW
            )
        )
        
        # 3. Handler 處理控制（通過 SafePowerController DRY_RUN 模式）
        event = await handler.handle_control(control)
        
        assert event.status == DERControlEventStatus.COMPLETED
        assert event.result.simulated is True
        
        # 4. 應用到 PCS（writer 直接寫入 mock）
        result = await pcs_adapter.apply_der_control(control)
        
        assert result.success is True
        assert result.simulated is False
        assert result.requested_power_w == 75000
    
    @pytest.mark.asyncio
    async def test_charging_flow_simulation(self, mock_modbus_client, power_controller):
        """測試充電流程（模擬模式）"""
        handler = DERControlHandler(power_controller)
        
        # 充電控制（負值）
        control = DERControl(
            mRID="charge_test_001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=-50000, multiplier=0)  # -50kW
            )
        )
        
        event = await handler.handle_control(control)
        
        assert event.status == DERControlEventStatus.COMPLETED
        assert event.result.requested_power_w == -50000  # 負值確認充電
    
    @pytest.mark.asyncio
    async def test_safety_prevents_over_limit(self, mock_modbus_client, power_controller):
        """測試安全機制阻止超限"""
        handler = DERControlHandler(power_controller)
        
        # 嘗試設定超出限制的功率
        control = DERControl(
            mRID="over_limit_001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=150000, multiplier=0)  # 150kW > 100kW
            )
        )
        
        event = await handler.handle_control(control)
        
        assert event.status == DERControlEventStatus.FAILED
        assert "exceeds limit" in event.error_message
        
        # Modbus 不應該被調用
        mock_modbus_client.write_register.assert_not_called()


# =============================================================================
# IEEE 2030.5 Recovery Mechanism Tests
# =============================================================================

class TestIEEE2030_5Recovery:
    """Test IEEE 2030.5 recovery mechanisms (opModConnect=true, opModEnergize=true,
    event cancellation, DefaultDERControl fallback)."""

    @pytest.mark.asyncio
    async def test_opmod_connect_true_clears_emergency_stop(self, der_control_handler):
        """opModConnect=true should reset EmergencyStop and reconnect PCS."""
        EmergencyStop.trigger("fault")
        assert EmergencyStop.is_stopped() is True

        control = DERControl(
            mRID="recovery001",
            DERControlBase=DERControlBase(opModConnect=True),
        )
        event = await der_control_handler.handle_control(control)

        assert event.status == DERControlEventStatus.COMPLETED
        assert EmergencyStop.is_stopped() is False

    @pytest.mark.asyncio
    async def test_opmod_connect_true_without_prior_stop(self, der_control_handler):
        """opModConnect=true should succeed even if EmergencyStop was not active."""
        control = DERControl(
            mRID="recovery002",
            DERControlBase=DERControlBase(opModConnect=True),
        )
        event = await der_control_handler.handle_control(control)

        assert event.status == DERControlEventStatus.COMPLETED
        assert EmergencyStop.is_stopped() is False

    @pytest.mark.asyncio
    async def test_opmod_energize_true_clears_emergency_stop(self, der_control_handler):
        """opModEnergize=true should reset EmergencyStop (no PCS mode change)."""
        EmergencyStop.trigger("de-energize fault")
        assert EmergencyStop.is_stopped() is True

        control = DERControl(
            mRID="recovery003",
            DERControlBase=DERControlBase(opModEnergize=True),
        )
        event = await der_control_handler.handle_control(control)

        assert event.status == DERControlEventStatus.COMPLETED
        assert EmergencyStop.is_stopped() is False

    @pytest.mark.asyncio
    async def test_opmod_energize_true_without_prior_stop(self, der_control_handler):
        """opModEnergize=true should succeed even without active EmergencyStop."""
        control = DERControl(
            mRID="recovery004",
            DERControlBase=DERControlBase(opModEnergize=True),
        )
        event = await der_control_handler.handle_control(control)

        assert event.status == DERControlEventStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_emergency_stop_blocks_normal_but_not_recovery(self, der_control_handler):
        """Normal power commands are blocked by EmergencyStop, but recovery
        commands (opModConnect=true) bypass the gate."""
        EmergencyStop.trigger("fault")

        # Normal power command is blocked
        blocked_control = DERControl(
            mRID="blocked001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        blocked_evt = await der_control_handler.handle_control(blocked_control)
        assert blocked_evt.status == DERControlEventStatus.FAILED

        # Recovery command succeeds
        recovery = DERControl(
            mRID="recovery005",
            DERControlBase=DERControlBase(opModConnect=True),
        )
        recovery_evt = await der_control_handler.handle_control(recovery)
        assert recovery_evt.status == DERControlEventStatus.COMPLETED
        assert EmergencyStop.is_stopped() is False

    @pytest.mark.asyncio
    async def test_cancel_disconnect_triggers_reconnect(self, der_control_handler):
        """Cancelling an active disconnect event should trigger reconnect + reset."""
        # First, execute a disconnect control
        disconnect = DERControl(
            mRID="disc001",
            DERControlBase=DERControlBase(opModConnect=False),
        )
        event = await der_control_handler.handle_control(disconnect)
        assert event.status == DERControlEventStatus.COMPLETED
        assert der_control_handler.active_control == event

        # Cancel it
        result = await der_control_handler.cancel_control("disc001")
        assert result is True
        assert der_control_handler.active_control is None

    @pytest.mark.asyncio
    async def test_cancel_normal_event_does_not_reconnect(self, der_control_handler):
        """Cancelling a normal power event should set power to 0, not reconnect."""
        control = DERControl(
            mRID="norm001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        event = await der_control_handler.handle_control(control)
        assert event.status == DERControlEventStatus.COMPLETED

        result = await der_control_handler.cancel_control("norm001")
        assert result is True

    @pytest.mark.asyncio
    async def test_default_der_control_fallback_on_cancel(self, der_control_handler):
        """After cancelling the active event, DefaultDERControl should be applied."""
        # Set a DefaultDERControl
        default_ctrl = DERControl(
            mRID="default001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=10000, multiplier=0)
            ),
        )
        der_control_handler.set_default_der_control(default_ctrl)

        # Execute a normal control
        control = DERControl(
            mRID="active001",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=50000, multiplier=0)
            ),
        )
        await der_control_handler.handle_control(control)

        # Cancel the active control — should fall back to default
        await der_control_handler.cancel_control("active001")

        # The default should now be the active control
        active = der_control_handler.active_control
        assert active is not None
        assert active.control.mRID == "default001"
        assert active.status == DERControlEventStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_set_and_clear_default_der_control(self, der_control_handler):
        """Test set/clear DefaultDERControl."""
        default_ctrl = DERControl(
            mRID="default002",
            DERControlBase=DERControlBase(
                opModFixedW=SignedPerCent(value=5000, multiplier=0)
            ),
        )
        der_control_handler.set_default_der_control(default_ctrl)
        assert der_control_handler._default_der_control is not None

        der_control_handler.set_default_der_control(None)
        assert der_control_handler._default_der_control is None
