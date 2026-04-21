import asyncio
import logging
from bms_2030_5_client.modbus.register_writer import ModbusRegisterWriter, WriteResult

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_address_alignment():
    # Initialize writer in simulation mode
    writer = ModbusRegisterWriter(host="127.0.0.1", port=502, simulation_mode=True)
    
    # Test Case: Logical address 4000 should result in physical address 3999
    logical_addr = 4000
    test_value = 100.0
    
    logger.info(f"Testing logical address {logical_addr}...")
    result = await writer.write(
        address=logical_addr,
        value=test_value,
        datatype="int16"
    )
    
    print(f"Logical Address: {logical_addr}")
    print(f"Result Physical Address: {result.address}")
    
    if result.address == 3999:
        print("SUCCESS: Address alignment correct (4000 -> 3999)")
        return True
    else:
        print(f"FAILURE: Expected 3999, got {result.address}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_address_alignment())
    exit(0 if success else 1)
