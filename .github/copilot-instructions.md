# BMS/EMS Communication Protocol Guidelines

This project implements communication between BMS (Battery Management System) and EMS (Energy Management System) using IEEE 2030.5 standard.

## Protocol Reference Files

When working with this project, always refer to:
- `src/bms_2030_5_client/protocols/modbus_registers.py` - RS-485 and CUBE register definitions
- `src/bms_2030_5_client/protocols/can_messages.py` - CAN 2.0B message definitions
- `src/bms_2030_5_client/protocols/ieee2030_5_protocol.py` - IEEE 2030.5 Smart Energy Profile definitions

---

## IEEE 2030.5 Smart Energy Profile

Reference: IEEE Std 2030.5™-2023

### Overview
- **Architecture:** RESTful using HTTP/HTTPS
- **Content Types:** `application/sep+xml` or `application/sep-exi`
- **Security:** TLS 1.2+ with certificate-based authentication
- **Discovery:** mDNS/DNS-SD (`_sep2._tcp`)

### DER Types (Battery = Type 7)
| Value | Type |
|-------|------|
| 0 | Not Applicable |
| 4 | Photovoltaic (Solar) |
| 7 | **Battery Storage** ← BMS uses this |
| 8 | Electric Vehicle |

### Key Function Sets
- **DER:** Distributed Energy Resources (battery control)
- **Metering:** Energy usage data
- **MirrorUsagePoint:** Client-side meter upload
- **DemandResponse:** Load control

### Common URI Paths
| Path | Resource |
|------|----------|
| `/dcap` | Device Capability (root) |
| `/edev` | End Device List |
| `/der` | DER List |
| `/ders` | DER Status |
| `/dercap` | DER Capability |
| `/mup` | Mirror Usage Point |

### DER Control Modes (IEEE 1547)
- `opModFixedW` - Fixed active power
- `opModFixedVar` - Fixed reactive power
- `opModVoltVar` - Volt-VAR control
- `opModVoltWatt` - Volt-Watt control
- `opModFreqWatt` - Frequency-Watt control

### Value Conversions
- **Power:** `value × 10^multiplier` (Watts)
- **SOC:** 0-10000 represents 0.00%-100.00%
- **Voltage/Current:** Use multiplier for scaling

---

## RS-485 Modbus RTU (BMS Protocol V1.7)

- **Baud Rate:** 9600
- **Settings:** N, 8, 1
- **Function Codes:** Read(0x03), Write(0x06)
- **Refresh Time:** 500ms
- **Rack ID Range:** 1~24

### Basic Registers (0x0000-0x0010)
| Address | Name | Unit | Note |
|---------|------|------|------|
| 0x0000 | Heart Beat | - | 0.5s cycle |
| 0x0001 | Total Voltage | 0.1V | |
| 0x0002 | Total Current | 0.1A | Offset -1600A |
| 0x0003 | SOC | 0.1% | |
| 0x0008 | Error Status | bit | See ErrorStatusBits |
| 0x000E | Relay Switch | 0/1 | 1=ON |

---

## CUBE Modbus TCP/IP (V1.0.3)

- **Port:** 502
- **Address Offset:** Documentation addresses need **-1** for actual Modbus communication
- **7000 Series:** Rack-level data (30 registers per rack) → Actual: 6999 series
- **4000 Series:** System/Container-level data → Actual: 3999 series

### System Registers (4000 series in doc → 3999 series actual)
| Doc Addr | Actual | Name | Unit |
|----------|--------|------|------|
| 4000 | 3999 | Vol_avg | 0.1V |
| 4001 | 4000 | total_curr | 0.1A (S16) |
| 4002 | 4001 | total_power | 0.1kW (S16) |
| 4003 | 4002 | deliy_CHG | 0.1kWh |
| 4004 | 4003 | deliy_DSC | 0.1kWh |
| 4005 | 4004 | SOC_avg | 0.1% |
| 4006 | 4005 | RM_total | AH |
| 4007 | 4006 | FCC_total | AH |
| 4008 | 4007 | online_NO | N.A. |
| 4009 | 4008 | allow_power | 0.1kW |
| 4016 | 4015 | all_max_t | 1°C (S16) |
| 4017 | 4016 | all_min_t | 1°C (S16) |
| 4042 | 4041 | allow_power_DSC | 0.1kW |
| 4043 | 4042 | allow_power_CHG | 0.1kW |

### Rack Registers (7000 series in doc → 6999 series actual)
| Doc Addr | Actual | Name | Unit |
|----------|--------|------|------|
| 7000 | 6999 | rack_vol | 0.1V |
| 7001 | 7000 | rack_current | 0.1A (S16) |
| 7002 | 7001 | SOC | 0.1% |
| 7003 | 7002 | cell_max_v | 0.001V |
| 7004 | 7003 | cell_min_v | 0.001V |
| 7005 | 7004 | cell_max_t | 1°C (S16) |
| 7006 | 7005 | cell_min_t | 1°C (S16) |
| 7011 | 7010 | RM | 0.01AH |
| 7012 | 7011 | FCC | 0.01AH |
| 7019 | 7018 | lecu_flag | bitfield |
| 7020 | 7019 | rack_flag | bitfield |
| 7022 | 7021 | SOH | 1% |
| 7025 | 7024 | relay_sw | 0/1 |
| 7026 | 7025 | PF_release | 0/1 |

**Rack N address = Base + 30 × (N-1)**
- Rack 1: 6999 (actual), 7029 (actual for Rack 2), etc.

---

## CAN 2.0B

- **Baud Rate:** 500K
- **Data Length:** 8 bytes
- **ID Prefix:**
  - `0x0F` - Master read command
  - `0x0A` - Slave response
  - `0x01` - Master write command

---

## Data Conversion Rules

### Address Offset
- **CUBE Modbus:** Doc address - 1 = Actual Modbus address
  - Doc 4000 → Actual 3999
  - Doc 7000 → Actual 6999

### Voltage
- Total voltage: `raw × 0.1` (V)
- Cell voltage: `raw × 0.001` (V)

### Current
- BMS: `(raw - 16000) × 0.1` (A), Negative = Charging

### Temperature
- `raw - 40` (°C)

### Capacity
- RS-485: `raw × 0.01` (AH)
- CUBE Rack (RM/FCC): `raw × 0.01` (AH)
- CUBE System (RM_total/FCC_total): `raw` (AH, no scaling)

### SOC
- BMS: `raw × 0.1` (%)
- IEEE 2030.5: `raw / 100` (%)

---

## Error Status Bits (0x0008)

### Low Byte
- Bit 0: Level 2 Alarm
- Bit 1: Level 3 Alarm
- Bit 2: PF Protection
- Bit 3: Relay Stuck
- Bit 4: Voltage Alarm
- Bit 5: Temperature Alarm
- Bit 6: Current Alarm
- Bit 7: Communication Error

### High Byte
- Bit 0: Relay Status (1=ON)
- Bit 1: Fan Status (1=ON)
- Bit 2: Balance Error

---

## Code Examples

### BMS Protocol Usage
```python
from bms_2030_5_client.protocols import (
    RS485_REGISTERS,
    CUBE_RACK_REGISTERS,
    CUBE_SYSTEM_REGISTERS,
    CUBE_ADDRESS_OFFSET,
    CAN_READ_COMMANDS,
    ErrorStatusBits,
)

# Convert raw voltage
voltage = RS485_REGISTERS.convert_voltage(raw_value)

# Get rack 3 register address (uses actual Modbus addresses)
# Base is 6999 (doc 7000), offset is 30 per rack
addr = CUBE_RACK_REGISTERS.get_rack_address(
    CUBE_RACK_REGISTERS.RACK_VOLTAGE,  # 6999
    rack_number=3
)  # Returns 7059 (6999 + 30*2)

# Convert documentation address to actual
actual_addr = CUBE_SYSTEM_REGISTERS.doc_to_actual(4005)  # Returns 4004

# Check error flags
if status & ErrorStatusBits.VOLTAGE_ALARM:
    handle_voltage_alarm()
```

### IEEE 2030.5 Usage
```python
from bms_2030_5_client.protocols import (
    IEEE2030_5_CONFIG,
    DERType,
    URIPaths,
    UnitOfMeasure,
    soc_to_sep_value,
    watts_to_sep_value,
)

# Battery storage type
der_type = DERType.BATTERY_STORAGE  # 7

# Build DER status URI
der_status_uri = URIPaths.for_der("der123", URIPaths.DER_STATUS)

# Convert values for IEEE 2030.5
soc_sep = soc_to_sep_value(85.5)  # 8550
power_value, power_mult = watts_to_sep_value(5000)  # 5kW
```

---

## Testing Guidelines

- Use mock Modbus server for unit tests
- Validate all register conversions
- Test boundary values (0, max, negative)
- Verify bitfield parsing
- Test IEEE 2030.5 XML serialization
