import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from bms_2030_5_client.core.sep_client import (ConnectionError, SepClient,
                                                TLSError)
from bms_2030_5_client.ieee2030_5.xml_utils import xml_to_dataclass
from bms_2030_5_client.models.ieee2030_5_models import Time
from bms_2030_5_client.runtime_config import TLSConfig

# 檢查是否設定了整合測試所需的環境變數
# 若未設定，將跳過此模組中的所有測試
pytestmark = pytest.mark.skipif(
    not all(os.getenv(var) for var in [
        "TEST_SEP_SERVER_URL",
        "TEST_CLIENT_CERT_PATH",
        "TEST_CLIENT_KEY_PATH",
        "TEST_CA_CERT_PATH"
    ]),
    reason="需要設定整合測試的環境變數 (TEST_SEP_SERVER_URL, TEST_CLIENT_CERT_PATH, etc.)"
)


@pytest.fixture(scope="module")
def event_loop():
    """為整個模組提供一個 asyncio 事件循環"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def tls_config() -> TLSConfig:
    """從環境變數建立 TLS 設定"""
    return TLSConfig(
        cafile=Path(os.environ["TEST_CA_CERT_PATH"]),
        certfile=Path(os.environ["TEST_CLIENT_CERT_PATH"]),
        keyfile=Path(os.environ["TEST_CLIENT_KEY_PATH"]),
    )


@pytest.fixture(scope="module")
async def sep_client(tls_config: TLSConfig) -> SepClient:
    """建立並返回一個 SepClient 實例"""
    client = SepClient(
        base_url=os.environ["TEST_SEP_SERVER_URL"],
        tls_config=tls_config,
        profile_config=None,  # 使用預設設定
    )
    yield client
    await client.close()


@pytest.mark.integration
class TestTimeSync:
    """時間同步 E2B 整合測試套件"""

    async def test_get_time_success(self, sep_client: SepClient):
        """
        測試案例：成功獲取並驗證時間
        - 驗證能與伺服器建立 mTLS 連線並取得 /tm 資源
        - 驗證回應為 HTTP 200 OK
        - 驗證能將 XML 解析為 Time 物件
        - 驗證 currentTime 與本地 UTC 時間誤差在 5 秒內
        - 驗證 quality > 0
        """
        response = await sep_client.get("/tm")
        assert response.is_success, f"預期 HTTP 200 OK，但收到 {response.status_code}"

        time_obj = xml_to_dataclass(response.body, Time)
        assert isinstance(time_obj, Time)

        # 驗證時間戳
        now_utc_ts = datetime.now(timezone.utc).timestamp()
        time_diff = abs(time_obj.currentTime - now_utc_ts)
        assert time_diff < 5, f"時間誤差過大: {time_diff:.2f} 秒"

        # 驗證時鐘品質
        assert time_obj.quality > 0, f"預期時鐘品質 > 0，但得到 {time_obj.quality}"

    async def test_connection_failure(self, tls_config: TLSConfig):
        """測試案例：處理連線失敗"""
        # 使用一個無效的位址來觸發連線錯誤
        bad_client = SepClient(
            base_url="https://127.0.0.1:1",  # 假設此埠號未被使用
            tls_config=tls_config,
            profile_config=None,
        )
        with pytest.raises(ConnectionError):
            await bad_client.get("/tm")
        await bad_client.close()

    async def test_tls_handshake_failure(self):
        """測試案例：處理 TLS 握手失敗（使用無效憑證）"""
        # 建立一個指向有效 CA 但本身無效的憑證設定
        invalid_tls_config = TLSConfig(
            cafile=Path(os.environ["TEST_CA_CERT_PATH"]),
            certfile=Path("/dev/null"),  # 無效的憑證檔案
            keyfile=Path("/dev/null"),
        )
        bad_client = SepClient(
            base_url=os.environ["TEST_SEP_SERVER_URL"],
            tls_config=invalid_tls_config,
            profile_config=None,
        )
        with pytest.raises(TLSError):
            await bad_client.get("/tm")
        await bad_client.close()