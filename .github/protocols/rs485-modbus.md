# RS-485 Modbus RTU (BMS Protocol V1.7)

- **Baud Rate:** 9600
- **Settings:** N, 8, 1
- **Function Codes:** Read(0x03), Write(0x06)
- **Refresh Time:** 500ms
- **Rack ID Range:** 1~24

## Basic Registers (0x0000-0x0010)
| Address | Name | Unit | Note |
|---------|------|------|------|
| 0x0000 | Heart Beat | - | 0.5s cycle |
| 0x0001 | Total Voltage | 0.1V | |
| 0x0002 | Total Current | 0.1A | Offset -1600A |
| 0x0003 | SOC | 0.1% | |
| 0x0008 | Error Status | bit | See ErrorStatusBits |
| 0x000E | Relay Switch | 0/1 | 1=ON |

---

# CAN 2.0B

- **Baud Rate:** 500K
- **Data Length:** 8 bytes
- **ID Prefix:**
  - `0x0F` - Master read command
  - `0x0A` - Slave response
  - `0x01` - Master write command
