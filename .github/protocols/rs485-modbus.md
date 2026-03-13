# RS-485 Modbus RTU (BMS Protocol V1.7)

- **Baud Rate:** 9600
- **Settings:** N, 8, 1
- **Function Codes:** Read(0x03), Write(0x06)
- **Refresh Time:** 500ms
- **Rack ID Range:** 1~24

> ⚠️ **本系統不使用 RS-485 通道做控制操作。**
> RS-485 僅用於 BMS 資料讀取（SOC、電壓、電流、溫度等）。
> 所有功率控制和模式切換操作均透過 PCS Modbus TCP（40000 系列暫存器）執行。
> `RELAY_SWITCH` (0x000E) 屬於 RS-485 暫存器，IEEE 2030.5 `opModConnect=false` **不操作此暫存器**，
> 改為透過 PCS TCP 將 `OPERATION_MODE` (40010) 設為 `STANDBY(0)` 實現斷開控制。

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
