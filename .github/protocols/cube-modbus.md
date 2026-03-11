# CUBE Modbus TCP/IP (V1.0.3)

- **Port:** 502
- **Address Offset:** Documentation addresses need **-1** for actual Modbus communication
- **7000 Series:** Rack-level data (30 registers per rack) → Actual: 6999 series
- **4000 Series:** System/Container-level data → Actual: 3999 series

## System Registers (4000 series in doc → 3999 series actual)
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

## Rack Registers (7000 series in doc → 6999 series actual)
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
