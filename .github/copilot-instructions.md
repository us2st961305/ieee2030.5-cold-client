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
- **7000 Series:** Rack-level data (30 registers per rack)
- **4000 Series:** System-level data

### Rack Registers (7000 series)
| Base | Name | Unit |
|------|------|------|
| 7000 | Rack Voltage | 0.1V |
| 7001 | Rack Current | 0.1A |
| 7002 | SOC | 0.1% |
| 7019 | LECU Flag | bit |
| 7020 | Rack Flag | bit |
| 7025 | Relay Switch | 0/1 |

**Rack N address = Base + 30 × (N-1)**

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

### Voltage
- Total voltage: `raw × 0.1` (V)
- Cell voltage: `raw × 0.001` (V)

### Current
- BMS: `(raw - 16000) × 0.1` (A), Negative = Charging

### Temperature
- `raw - 40` (°C)

### Capacity
- RS-485: `raw × 0.01` (AH)
- CUBE: `raw × 0.1` (AH)

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
    CAN_READ_COMMANDS,
    ErrorStatusBits,
)

# Convert raw voltage
voltage = RS485_REGISTERS.convert_voltage(raw_value)

# Get rack 3 register address
addr = CUBE_RACK_REGISTERS.get_rack_address(
    CUBE_RACK_REGISTERS.SOC, 
    rack_number=3
)

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
