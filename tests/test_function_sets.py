"""
Tests for IEEE 2030.5-2023 Function Set models.

Phase 10: Testing for all new models added in the refactoring.
"""

import pytest
from datetime import datetime
import time


# =============================================================================
# Test DER Control Types (Phase 1)
# =============================================================================

class TestDERControlTypes:
    """Tests for DERControlType and DERControlType2."""
    
    def test_der_control_type_flags(self):
        """Test DERControlType bit flags."""
        from bms_2030_5_client.models import DERControlType
        
        # Test individual flags
        assert DERControlType.opModConnect.value == 1 << 0
        assert DERControlType.opModEnergize.value == 1 << 1
        assert DERControlType.opModMaxLimW.value == 1 << 2
        
        # Test combined flags
        combined = DERControlType.opModConnect | DERControlType.opModMaxLimW
        assert combined.value == 0b101
        assert DERControlType.opModConnect in combined
        assert DERControlType.opModMaxLimW in combined
        assert DERControlType.opModEnergize not in combined
    
    def test_der_control_type2_flags(self):
        """Test DERControlType2 bit flags."""
        from bms_2030_5_client.models import DERControlType2
        
        assert DERControlType2.opModFreqDroop.value == 1 << 0
        assert DERControlType2.opModVoltWatt.value == 1 << 1
        
    def test_control_type_to_mode_names(self):
        """Test conversion to human-readable names."""
        from bms_2030_5_client.models import (
            DERControlType, 
            control_type_to_mode_names
        )
        
        control = DERControlType.opModConnect | DERControlType.opModMaxLimW
        names = control_type_to_mode_names(control)
        
        assert "opModConnect" in names
        assert "opModMaxLimW" in names
        assert len(names) == 2
    
    def test_der_control_base_complete(self):
        """Test DERControlBaseComplete dataclass."""
        from bms_2030_5_client.models import (
            DERControlBaseComplete,
            ActivePowerControlType,
        )
        
        control_base = DERControlBaseComplete(
            opModConnect=True,
            opModMaxLimW=ActivePowerControlType(maxLimW=5000, multiplier=0),
        )
        
        assert control_base.opModConnect is True
        assert control_base.opModMaxLimW.maxLimW == 5000
    
    def test_active_power_control_type(self):
        """Test ActivePowerControlType."""
        from bms_2030_5_client.models import ActivePowerControlType
        
        apc = ActivePowerControlType(maxLimW=1000, multiplier=3)  # 1000 kW
        assert apc.maxLimW == 1000
        assert apc.multiplier == 3
        
        # Test JSON serialization
        json_str = apc.to_json()
        restored = ActivePowerControlType.from_json(json_str)
        assert restored.maxLimW == 1000


# =============================================================================
# Test DER Curves (Phase 2)
# =============================================================================

class TestDERCurves:
    """Tests for DER Curve models."""
    
    def test_der_curve_type_enum(self):
        """Test DERCurveType enumeration."""
        from bms_2030_5_client.models import DERCurveType
        
        assert DERCurveType.opModVoltVar.value == 0
        assert DERCurveType.opModFreqWatt.value == 1
        assert DERCurveType.opModLVRTMomentaryCessation.value == 4
        
    def test_curve_data(self):
        """Test CurveData dataclass."""
        from bms_2030_5_client.models import CurveData
        
        cd = CurveData(xvalue=100, yvalue=50)
        assert cd.xvalue == 100
        assert cd.yvalue == 50
    
    def test_der_curve_creation(self):
        """Test DERCurve creation and serialization."""
        from bms_2030_5_client.models import (
            DERCurve,
            DERCurveType,
            CurveData,
        )
        
        curve = DERCurve(
            mRID="curve-001",
            curveType=DERCurveType.opModVoltVar,
            curveData=[
                CurveData(xvalue=92, yvalue=44),
                CurveData(xvalue=98, yvalue=0),
                CurveData(xvalue=102, yvalue=0),
                CurveData(xvalue=108, yvalue=-44),
            ],
        )
        
        assert curve.mRID == "curve-001"
        assert curve.curveType == DERCurveType.opModVoltVar
        assert len(curve.curveData) == 4
    
    def test_curve_interpolation(self):
        """Test curve interpolation."""
        from bms_2030_5_client.models import DERCurve, DERCurveType, CurveData
        
        curve = DERCurve(
            mRID="test-curve",
            curveType=DERCurveType.opModVoltVar,
            curveData=[
                CurveData(xvalue=92, yvalue=44),
                CurveData(xvalue=100, yvalue=0),
                CurveData(xvalue=108, yvalue=-44),
            ],
        )
        
        # Test interpolation
        assert curve.interpolate(92) == 44
        assert curve.interpolate(108) == -44
        assert curve.interpolate(100) == 0
        
        # Mid-point interpolation
        assert curve.interpolate(96) == 22  # Half way between 44 and 0
        
        # Beyond boundaries
        assert curve.interpolate(80) == 44  # Before first point
        assert curve.interpolate(120) == -44  # After last point
    
    def test_create_volt_var_curve(self):
        """Test Volt-VAR curve factory."""
        from bms_2030_5_client.models import create_volt_var_curve
        
        curve = create_volt_var_curve(
            mRID="vv-001",
            v1=92, q1=44,
            v2=98, q2=0,
            v3=102, q3=0,
            v4=108, q4=-44,
        )
        
        assert curve.curveType.value == 0  # opModVoltVar
        assert len(curve.curveData) == 4
    
    def test_ieee1547_default_volt_var(self):
        """Test IEEE 1547 default Volt-VAR curve."""
        from bms_2030_5_client.models import create_ieee1547_default_volt_var
        
        curve = create_ieee1547_default_volt_var()
        
        assert curve.mRID == "ieee1547-default-volt-var"
        assert len(curve.curveData) == 4


# =============================================================================
# Test DRLC Models (Phase 3)
# =============================================================================

class TestDRLCModels:
    """Tests for DRLC Function Set models."""
    
    def test_device_category_type(self):
        """Test DeviceCategoryType bit flags."""
        from bms_2030_5_client.models import DeviceCategoryType
        
        assert DeviceCategoryType.PROGRAMMABLE_THERMOSTAT.value == 1 << 0
        assert DeviceCategoryType.ELECTRIC_VEHICLE.value == 1 << 11
        
        # Test combined categories
        combined = (
            DeviceCategoryType.ELECTRIC_VEHICLE | 
            DeviceCategoryType.BATTERY_STORAGE
        )
        assert DeviceCategoryType.ELECTRIC_VEHICLE in combined
        assert DeviceCategoryType.BATTERY_STORAGE in combined
    
    def test_end_device_control(self):
        """Test EndDeviceControl creation."""
        from bms_2030_5_client.models import (
            EndDeviceControl,
            DeviceCategoryType,
            DutyCycleType,
        )
        
        edc = EndDeviceControl(
            mRID="edc-001",
            deviceCategory=DeviceCategoryType.WATER_HEATER,
            drProgramMandatory=False,
            loadShiftForward=True,
            dutyCycle=DutyCycleType(normalValue=50),
        )
        
        assert edc.mRID == "edc-001"
        assert edc.loadShiftForward is True
        assert edc.dutyCycle.normalValue == 50
    
    def test_create_load_control_event(self):
        """Test load control event factory."""
        from bms_2030_5_client.models import (
            create_load_control_event,
            DeviceCategoryType,
        )
        
        event = create_load_control_event(
            mRID="lc-001",
            description="Peak reduction",
            device_category=DeviceCategoryType.WATER_HEATER,
            duty_cycle=50,
            start_time=int(time.time()),
            duration=3600,
        )
        
        assert event.mRID == "lc-001"
        assert event.dutyCycle.normalValue == 50


# =============================================================================
# Test Messaging Models (Phase 4)
# =============================================================================

class TestMessagingModels:
    """Tests for Messaging Function Set models."""
    
    def test_priority_type(self):
        """Test PriorityType enumeration."""
        from bms_2030_5_client.models import PriorityType
        
        assert PriorityType.LOW.value == 0
        assert PriorityType.NORMAL.value == 1
        assert PriorityType.HIGH.value == 2
        assert PriorityType.CRITICAL.value == 3
    
    def test_text_message(self):
        """Test TextMessage creation."""
        from bms_2030_5_client.models import TextMessage, PriorityType
        
        msg = TextMessage(
            mRID="msg-001",
            textMessage="Test message",
            priority=PriorityType.HIGH,
        )
        
        assert msg.textMessage == "Test message"
        assert msg.priority == PriorityType.HIGH
    
    def test_create_alert_message(self):
        """Test alert message factory."""
        from bms_2030_5_client.models import create_alert_message
        
        msg = create_alert_message(
            mRID="alert-001",
            text="Warning: High temperature detected",
        )
        
        assert msg.priority.value == 2  # HIGH


# =============================================================================
# Test File Models (Phase 5)
# =============================================================================

class TestFileModels:
    """Tests for File Function Set models."""
    
    def test_file_type(self):
        """Test FileType enumeration."""
        from bms_2030_5_client.models import FileType
        
        assert FileType.FIRMWARE.value == 0
        assert FileType.CONFIGURATION.value == 1
    
    def test_file_status_type(self):
        """Test FileStatusType enumeration."""
        from bms_2030_5_client.models import FileStatusType
        
        assert FileStatusType.PENDING.value == 0
        assert FileStatusType.COMPLETED.value == 3
    
    def test_file_creation(self):
        """Test File resource creation."""
        from bms_2030_5_client.models import File, FileType
        
        f = File(
            mRID="file-001",
            fileURI="https://server.com/firmware/v2.0.bin",
            fileType=FileType.FIRMWARE,
            size=1048576,  # 1 MB
        )
        
        assert f.fileURI.startswith("https://")
        assert f.size == 1048576
    
    def test_create_firmware_image(self):
        """Test firmware image factory."""
        from bms_2030_5_client.models import create_firmware_image
        
        fw = create_firmware_image(
            mRID="fw-001",
            uri="https://server.com/fw/v2.1.bin",
            size=2097152,
            version="2.1.0",
            sha256="abcd1234...",
        )
        
        assert fw.fileType.value == 0  # FIRMWARE


# =============================================================================
# Test Flow Reservation Models (Phase 6)
# =============================================================================

class TestFlowReservationModels:
    """Tests for Flow Reservation Function Set models."""
    
    def test_signed_real_energy(self):
        """Test SignedRealEnergy dataclass."""
        from bms_2030_5_client.models import SignedRealEnergy
        
        energy = SignedRealEnergy(value=50000, multiplier=0)  # 50 kWh
        
        assert energy.value == 50000
        assert energy.get_watt_hours() == 50000
        
        # Test factory
        energy2 = SignedRealEnergy.from_kwh(50)
        assert energy2.value == 50000
    
    def test_flow_reservation_request(self):
        """Test FlowReservationRequest creation."""
        from bms_2030_5_client.models import (
            FlowReservationRequest,
            SignedRealEnergy,
            RequestedActivePower,
        )
        
        request = FlowReservationRequest(
            mRID="frr-001",
            description="EV Charging",
            energyRequested=SignedRealEnergy.from_kwh(60),
            powerRequested=RequestedActivePower.from_kw(7.7),
            durationRequested=28800,  # 8 hours
        )
        
        assert request.mRID == "frr-001"
        assert request.durationRequested == 28800
    
    def test_create_charging_request(self):
        """Test charging request factory."""
        from bms_2030_5_client.models import create_charging_request
        
        request = create_charging_request(
            mRID="ev-charge-001",
            energy_kwh=50,
            power_kw=7.7,
            duration_hours=8,
            description="Night charging",
        )
        
        assert request.energyRequested.get_watt_hours() == 50000
    
    def test_calculate_required_charging_time(self):
        """Test charging time calculation."""
        from bms_2030_5_client.models import calculate_required_charging_time
        
        # 50 kWh at 10 kW = 5 hours = 18000 seconds
        time_sec = calculate_required_charging_time(50, 10)
        assert time_sec == 18000
        
        # With efficiency 90%
        time_sec_eff = calculate_required_charging_time(50, 10, efficiency=0.9)
        assert time_sec_eff == 20000  # 50 / (10 * 0.9) * 3600


# =============================================================================
# Test Pricing Models (Phase 7)
# =============================================================================

class TestPricingModels:
    """Tests for Pricing Function Set models."""
    
    def test_currency_type(self):
        """Test CurrencyType enumeration."""
        from bms_2030_5_client.models import CurrencyType
        
        assert CurrencyType.USD.value == 840
        assert CurrencyType.EUR.value == 978
        assert CurrencyType.TWD.value == 901
    
    def test_price_value(self):
        """Test PriceValue dataclass."""
        from bms_2030_5_client.models import PriceValue, CurrencyType
        
        # $5.34 = 534 cents
        price = PriceValue(
            value=534,
            multiplier=-2,
            currency=CurrencyType.USD,
        )
        
        assert price.to_currency_units() == 5.34
        
        # Test factory
        price2 = PriceValue.from_currency(3.85, CurrencyType.TWD)
        assert abs(price2.to_currency_units() - 3.85) < 0.01
    
    def test_tariff_profile(self):
        """Test TariffProfile creation."""
        from bms_2030_5_client.models import (
            TariffProfile,
            TariffType,
            CurrencyType,
        )
        
        tariff = TariffProfile(
            mRID="tp-001",
            description="TOU Tariff",
            tariffType=TariffType.TOU,
            currency=CurrencyType.TWD,
        )
        
        assert tariff.mRID == "tp-001"
        assert tariff.tariffType == TariffType.TOU
    
    def test_calculate_cost(self):
        """Test cost calculation."""
        from bms_2030_5_client.models import calculate_cost, CurrencyType
        
        # 100 kWh at $0.15/kWh = $15.00
        cost = calculate_cost(100, 0.15, CurrencyType.USD)
        
        assert cost.consumption_kwh == 100
        assert cost.total_cost == 15.00
        assert cost.currency == CurrencyType.USD


# =============================================================================
# Test Prepayment Models (Phase 8)
# =============================================================================

class TestPrepaymentModels:
    """Tests for Prepayment Function Set models."""
    
    def test_account_status_type(self):
        """Test AccountStatusType enumeration."""
        from bms_2030_5_client.models import AccountStatusType
        
        assert AccountStatusType.NORMAL.value == 0
        assert AccountStatusType.LOW_BALANCE.value == 1
        assert AccountStatusType.DISCONNECTED.value == 5
    
    def test_account_balance(self):
        """Test AccountBalance dataclass."""
        from bms_2030_5_client.models import (
            AccountBalance,
            AccountStatusType,
            PriceValue,
            CurrencyType,
        )
        
        balance = AccountBalance(
            availableCredit=PriceValue.from_currency(1234.56, CurrencyType.TWD),
            creditStatus=AccountStatusType.NORMAL,
            emergencyCreditEnabled=True,
            emergencyCreditRemaining=PriceValue.from_currency(200, CurrencyType.TWD),
        )
        
        assert abs(balance.get_available_credit() - 1234.56) < 0.01
        assert balance.is_low_balance() is False
    
    def test_credit_register(self):
        """Test CreditRegister creation."""
        from bms_2030_5_client.models import (
            CreditRegister,
            CreditTypeType,
            PriceValue,
            CurrencyType,
        )
        
        credit = CreditRegister(
            mRID="cr-001",
            creditType=CreditTypeType.REGULAR,
            creditAmount=PriceValue.from_currency(500, CurrencyType.TWD),
            token="TKN-2025-0001",
        )
        
        assert credit.get_credit_amount() == 500
        assert credit.token == "TKN-2025-0001"
    
    def test_create_prepay_account(self):
        """Test prepay account factory."""
        from bms_2030_5_client.models import (
            create_prepay_account,
            CurrencyType,
        )
        
        account = create_prepay_account(
            mRID="pa-001",
            description="Test Account",
            low_credit_warning=100,
            currency=CurrencyType.TWD,
        )
        
        assert account.mRID == "pa-001"
        assert account.currency == CurrencyType.TWD
    
    def test_estimate_remaining_usage(self):
        """Test remaining usage estimation."""
        from bms_2030_5_client.models import estimate_remaining_usage
        
        # $100 balance, $5/kWh rate, 20 kWh/day usage
        result = estimate_remaining_usage(100, 5, 20)
        
        assert result["remaining_kwh"] == 20  # 100 / 5
        assert result["remaining_days"] == 1  # 20 kWh / 20 kWh per day
        assert result["remaining_hours"] == 24


# =============================================================================
# Test Model Serialization
# =============================================================================

class TestModelSerialization:
    """Tests for model JSON serialization."""
    
    def test_der_curve_json_roundtrip(self):
        """Test DERCurve JSON serialization roundtrip."""
        from bms_2030_5_client.models import (
            DERCurve,
            DERCurveType,
            CurveData,
        )
        
        original = DERCurve(
            mRID="test-curve",
            curveType=DERCurveType.opModVoltVar,
            curveData=[
                CurveData(xvalue=92, yvalue=44),
                CurveData(xvalue=108, yvalue=-44),
            ],
        )
        
        json_str = original.to_json()
        restored = DERCurve.from_json(json_str)
        
        assert restored.mRID == original.mRID
        assert len(restored.curveData) == 2
    
    def test_end_device_control_json_roundtrip(self):
        """Test EndDeviceControl JSON serialization."""
        from bms_2030_5_client.models import (
            EndDeviceControl,
            DeviceCategoryType,
        )
        
        original = EndDeviceControl(
            mRID="edc-test",
            deviceCategory=DeviceCategoryType.ELECTRIC_VEHICLE,
        )
        
        json_str = original.to_json()
        restored = EndDeviceControl.from_json(json_str)
        
        assert restored.mRID == original.mRID
    
    def test_tariff_profile_json_roundtrip(self):
        """Test TariffProfile JSON serialization."""
        from bms_2030_5_client.models import (
            TariffProfile,
            TariffType,
            CurrencyType,
        )
        
        original = TariffProfile(
            mRID="tp-test",
            tariffType=TariffType.TOU,
            currency=CurrencyType.TWD,
        )
        
        json_str = original.to_json()
        restored = TariffProfile.from_json(json_str)
        
        assert restored.mRID == original.mRID
        assert restored.currency == CurrencyType.TWD
