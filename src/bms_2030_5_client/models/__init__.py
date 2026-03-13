"""
Data models package.
"""

from bms_2030_5_client.models.bms_models import (
    RackData,
    RackStatus,
    SystemData,
    BMSSnapshot,
    AlarmLevel,
)

# IEEE 2030.5-2023 DER Control Types (Phase 1: Complete DERControlBase)
from bms_2030_5_client.models.der_control_types import (
    # DERControlType Bit Flags
    DERControlType,
    DERControlType2,
    # Control Value Types
    SignedPerCentControlType,
    PerCentControlType,
    ActivePowerControlType,
    UnsignedActivePowerControlType,
    ActivePowerDeltaControlType,
    ReactivePowerControlType,
    UnsignedReactivePowerControlType,
    ReactivePowerDeltaControlType,
    FixedVarControlType,
    UnsignedFixedVarControlType,
    PowerFactorWithExcitationControlType,
    ApparentPowerControlType,
    FreqDroopControlType,
    VoltageControlType,
    # Complete DERControlBase
    DERControlBaseComplete,
    # Helper Functions
    control_type_to_mode_names,
    control_type2_to_mode_names,
)

# IEEE 2030.5-2023 DER Curves (Phase 2: DERCurve Support)
from bms_2030_5_client.models.der_curves import (
    # Curve Types
    DERCurveType,
    CurveData,
    DERCurve,
    DERCurveList,
    # Factory Functions
    create_volt_var_curve,
    create_freq_watt_curve,
    create_volt_watt_curve,
    create_watt_pf_curve,
    create_lvrt_curve,
    create_hvrt_curve,
    create_lfrt_curve,
    create_hfrt_curve,
    # IEEE 1547-2018 Default Curves
    create_ieee1547_default_volt_var,
    create_ieee1547_default_volt_watt,
    create_ieee1547_category_i_lvrt,
    create_ieee1547_category_ii_lvrt,
    create_ieee1547_category_iii_lvrt,
)

# IEEE 2030.5-2023 DRLC Function Set (Phase 3: Demand Response Load Control)
from bms_2030_5_client.models.drlc_models import (
    # Device Category
    DeviceCategoryType,
    # Appliance Load Reduction
    ApplianceLoadReductionType,
    ApplianceLoadReduction,
    # Control Types
    DutyCycleType,
    SetPointType,
    OffsetType,
    TargetReductionType,
    TargetReductionTypeEnum,
    # Load Shed Availability
    LoadShedAvailability,
    LoadShedAvailabilityList,
    # End Device Control (Load Control Events)
    EndDeviceControl,
    EndDeviceControlList,
    # Demand Response Program
    DemandResponseProgram,
    DemandResponseProgramList,
    # DR Event Response
    DREventResponseStatus,
    DrEventResponse,
    DrEventResponseList,
    # Helper Functions
    device_category_to_names,
    create_load_control_event,
    create_thermostat_event,
    create_ev_charging_event,
)

# IEEE 2030.5-2023 Messaging Function Set (Phase 4)
from bms_2030_5_client.models.messaging_models import (
    # Priority and Status
    PriorityType,
    MessageStatus,
    # Text Message
    TextMessage,
    TextMessageList,
    ActiveTextMessageList,
    # Messaging Program
    MessagingProgram,
    MessagingProgramList,
    # Message Response
    MessageResponseStatus,
    TextMessageResponse,
    TextMessageResponseList,
    # Helper Functions
    create_text_message,
    create_alert_message,
    create_info_message,
    create_maintenance_message,
    filter_messages_by_locale,
)

# IEEE 2030.5-2023 File Function Set (Phase 5)
from bms_2030_5_client.models.file_models import (
    # File Type and Status
    FileType,
    FileStatusType,
    ActivationStatusType,
    # File Status
    FileStatus,
    FileStatusList,
    # File Resource
    File,
    FileList,
    # Download Progress (Client-side)
    FileDownloadProgress,
    FirmwareUpdateRequest,
    # Helper Functions
    create_file_resource,
    create_firmware_image,
    create_config_file,
    get_mime_type_for_file_type,
)

# IEEE 2030.5-2023 Flow Reservation Function Set (Phase 6)
from bms_2030_5_client.models.flow_reservation_models import (
    # Status and Direction
    FlowReservationStatusType,
    EnergyFlowDirection,
    # Energy/Power Types
    SignedRealEnergy,
    RequestedActivePower,
    # Flow Reservation Request
    FlowReservationRequest,
    FlowReservationRequestList,
    # Flow Reservation Response
    FlowReservationResponse,
    FlowReservationResponseList,
    # Client Acknowledgment
    FlowReservationAckStatus,
    FlowReservationResponseResponse,
    FlowReservationResponseResponseList,
    # Helper Functions
    create_charging_request,
    create_discharging_request,
    create_reservation_response,
    calculate_required_charging_time,
)

# IEEE 2030.5-2023 Pricing Function Set (Phase 7)
from bms_2030_5_client.models.pricing_models import (
    # Currency and Tariff Types
    CurrencyType,
    TariffType,
    ConsumptionBlockType,
    TOUTierType,
    # Price Value
    PriceValue,
    # Consumption Tariff
    ConsumptionTariffInterval,
    ConsumptionTariffIntervalList,
    # Time Tariff
    TimeTariffInterval,
    TimeTariffIntervalList,
    # Rate Component
    RateComponent,
    RateComponentList,
    # Tariff Profile
    TariffProfile,
    TariffProfileList,
    # Price Summary
    PriceSummary,
    # Helper Functions
    create_tou_tariff,
    create_time_interval,
    create_consumption_tier,
    calculate_cost,
    get_current_price_summary,
)

# Phase 8: Prepayment Function Set
from bms_2030_5_client.models.prepayment_models import (
    # Status Types
    AccountStatusType,
    CreditTypeType,
    ServiceStatusType,
    # Account Balance
    AccountBalance,
    AccountBalanceList,
    # Credit Register
    CreditRegister,
    CreditRegisterList,
    # Operation Status
    PrepayOperationStatus,
    PrepayOperationStatusList,
    # Supply Override
    SupplyInterruptionOverride,
    SupplyInterruptionOverrideList,
    # Prepay Account
    PrepayAccount,
    PrepayAccountList,
    # Summary
    PrepaymentSummary,
    # Helper Functions
    create_prepay_account,
    create_credit_register,
    create_supply_override,
    get_prepayment_summary,
    estimate_remaining_usage,
)

from bms_2030_5_client.models.ieee2030_5_models import (
    Link,
    DER,
    DERList,
    DERCapability,
    DERSettings,
    DERStatus,
    DERAvailability,
    DERType,
    ConnectStatusType,
    OperationalModeStatusType,
    ActivePower,
    ReactivePower,
    Voltage,
    Current,
    StateOfCharge,
    ConnectStatusValue,
    OperationalModeStatusValue,
    InverterStatusValue,
    StorageModeStatusValue,
    AlarmStatusValue,
    Temperature,
    EndDevice,
    EndDeviceList,
    DeviceCapability,
    DeviceInformation,
    GPSLocationType,
    PowerSourceType,
    Time,
    Reading,
    MirrorMeterReading,
    MirrorMeterReadingList,
    # Metering models
    AccumulationBehaviourType,
    CommodityType,
    FlowDirectionType,
    DataQualifierType,
    KindType,
    UomType,
    ServiceKind,
    RoleFlagsType,
    DateTimeInterval,
    UnitValueType,
    ReadingType,
    MeterReading,
    MirrorReadingSet,
    MirrorUsagePoint,
    MirrorUsagePointList,
    # UsagePoint models (for server recovery)
    UsagePoint,
    UsagePointList,
    MeterReadingEntry,
    MeterReadingListResponse,
    # LogEvent models
    LogEvent,
    LogEventList,
    # DER Control models
    SignedPerCent,
    PerCent,
    DERControlBase,
    DERControl,
    DERControlList,
    DERProgram,
    DERProgramList,
    # FSA models
    FunctionSetAssignments,
    FunctionSetAssignmentsList,
    # Response models
    ResponseStatusType,
    DERControlResponse,
    ResponseSet,
    ResponseSetList,
    # Default DER Control
    DefaultDERControl,
    # Subscription / Notification models
    SubscriptionEncodingType,
    NotificationStatusType,
    Subscription,
    SubscriptionList,
    Notification,
    NotificationList,
    DERControlModesType,
    DERControlResponseFull,
)

__all__ = [
    # BMS models
    "RackData",
    "RackStatus",
    "SystemData",
    "BMSSnapshot",
    "AlarmLevel",
    # IEEE 2030.5-2023 DER Control Types (Phase 1)
    "DERControlType",
    "DERControlType2",
    "SignedPerCentControlType",
    "PerCentControlType",
    "ActivePowerControlType",
    "UnsignedActivePowerControlType",
    "ActivePowerDeltaControlType",
    "ReactivePowerControlType",
    "UnsignedReactivePowerControlType",
    "ReactivePowerDeltaControlType",
    "FixedVarControlType",
    "UnsignedFixedVarControlType",
    "PowerFactorWithExcitationControlType",
    "ApparentPowerControlType",
    "FreqDroopControlType",
    "VoltageControlType",
    "DERControlBaseComplete",
    "control_type_to_mode_names",
    "control_type2_to_mode_names",
    # IEEE 2030.5-2023 DER Curves (Phase 2)
    "DERCurveType",
    "CurveData",
    "DERCurve",
    "DERCurveList",
    "create_volt_var_curve",
    "create_freq_watt_curve",
    "create_volt_watt_curve",
    "create_watt_pf_curve",
    "create_lvrt_curve",
    "create_hvrt_curve",
    "create_lfrt_curve",
    "create_hfrt_curve",
    "create_ieee1547_default_volt_var",
    "create_ieee1547_default_volt_watt",
    "create_ieee1547_category_i_lvrt",
    "create_ieee1547_category_ii_lvrt",
    "create_ieee1547_category_iii_lvrt",
    # IEEE 2030.5-2023 DRLC Function Set (Phase 3)
    "DeviceCategoryType",
    "ApplianceLoadReductionType",
    "ApplianceLoadReduction",
    "DutyCycleType",
    "SetPointType",
    "OffsetType",
    "TargetReductionType",
    "TargetReductionTypeEnum",
    "LoadShedAvailability",
    "LoadShedAvailabilityList",
    "EndDeviceControl",
    "EndDeviceControlList",
    "DemandResponseProgram",
    "DemandResponseProgramList",
    "DREventResponseStatus",
    "DrEventResponse",
    "DrEventResponseList",
    "device_category_to_names",
    "create_load_control_event",
    "create_thermostat_event",
    "create_ev_charging_event",
    # IEEE 2030.5-2023 Messaging Function Set (Phase 4)
    "PriorityType",
    "MessageStatus",
    "TextMessage",
    "TextMessageList",
    "ActiveTextMessageList",
    "MessagingProgram",
    "MessagingProgramList",
    "MessageResponseStatus",
    "TextMessageResponse",
    "TextMessageResponseList",
    "create_text_message",
    "create_alert_message",
    "create_info_message",
    "create_maintenance_message",
    "filter_messages_by_locale",
    # IEEE 2030.5-2023 File Function Set (Phase 5)
    "FileType",
    "FileStatusType",
    "ActivationStatusType",
    "FileStatus",
    "FileStatusList",
    "File",
    "FileList",
    "FileDownloadProgress",
    "FirmwareUpdateRequest",
    "create_file_resource",
    "create_firmware_image",
    "create_config_file",
    "get_mime_type_for_file_type",
    # IEEE 2030.5-2023 Flow Reservation Function Set (Phase 6)
    "FlowReservationStatusType",
    "EnergyFlowDirection",
    "SignedRealEnergy",
    "RequestedActivePower",
    "FlowReservationRequest",
    "FlowReservationRequestList",
    "FlowReservationResponse",
    "FlowReservationResponseList",
    "FlowReservationAckStatus",
    "FlowReservationResponseResponse",
    "FlowReservationResponseResponseList",
    "create_charging_request",
    "create_discharging_request",
    "create_reservation_response",
    "calculate_required_charging_time",
    # IEEE 2030.5-2023 Pricing Function Set (Phase 7)
    "CurrencyType",
    "TariffType",
    "ConsumptionBlockType",
    "TOUTierType",
    "PriceValue",
    "ConsumptionTariffInterval",
    "ConsumptionTariffIntervalList",
    "TimeTariffInterval",
    "TimeTariffIntervalList",
    "RateComponent",
    "RateComponentList",
    "TariffProfile",
    "TariffProfileList",
    "PriceSummary",
    "create_tou_tariff",
    "create_time_interval",
    "create_consumption_tier",
    "calculate_cost",
    "get_current_price_summary",
    # IEEE 2030.5-2023 Prepayment Function Set (Phase 8)
    "AccountStatusType",
    "CreditTypeType",
    "ServiceStatusType",
    "AccountBalance",
    "AccountBalanceList",
    "CreditRegister",
    "CreditRegisterList",
    "PrepayOperationStatus",
    "PrepayOperationStatusList",
    "SupplyInterruptionOverride",
    "SupplyInterruptionOverrideList",
    "PrepayAccount",
    "PrepayAccountList",
    "PrepaymentSummary",
    "create_prepay_account",
    "create_credit_register",
    "create_supply_override",
    "get_prepayment_summary",
    "estimate_remaining_usage",
    # IEEE 2030.5 models
    "Link",
    "DER",
    "DERList",
    "DERCapability",
    "DERSettings",
    "DERStatus",
    "DERAvailability",
    "DERType",
    "ConnectStatusType",
    "OperationalModeStatusType",
    "ActivePower",
    "ReactivePower",
    "Voltage",
    "Current",
    "StateOfCharge",
    "ConnectStatusValue",
    "OperationalModeStatusValue",
    "InverterStatusValue",
    "StorageModeStatusValue",
    "Temperature",
    "EndDevice",
    "EndDeviceList",
    "DeviceCapability",
    "DeviceInformation",
    "GPSLocationType",
    "PowerSourceType",
    "Time",
    "Reading",
    "MirrorMeterReading",
    "MirrorMeterReadingList",
    # Metering models
    "AccumulationBehaviourType",
    "CommodityType",
    "FlowDirectionType",
    "DataQualifierType",
    "KindType",
    "UomType",
    "ServiceKind",
    "RoleFlagsType",
    "DateTimeInterval",
    "UnitValueType",
    "ReadingType",
    "MeterReading",
    "MirrorReadingSet",
    "MirrorUsagePoint",
    "MirrorUsagePointList",
    # LogEvent models
    "LogEvent",
    "LogEventList",
    # DER Control models
    "SignedPerCent",
    "PerCent",
    "DERControlBase",
    "DERControl",
    "DERControlList",
    "DERProgram",
    "DERProgramList",
    # FSA models
    "FunctionSetAssignments",
    "FunctionSetAssignmentsList",
    # Response models
    "ResponseStatusType",
    "DERControlResponse",
    "ResponseSet",
    "ResponseSetList",
    # Default DER Control
    "DefaultDERControl",
    # Subscription / Notification models
    "SubscriptionEncodingType",
    "NotificationStatusType",
    "Subscription",
    "SubscriptionList",
    "Notification",
    "NotificationList",
    "DERControlModesType",
    "DERControlResponseFull",
]