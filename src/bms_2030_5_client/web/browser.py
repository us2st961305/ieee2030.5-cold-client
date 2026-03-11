"""
IEEE 2030.5 Resource Browser.

Provides endpoints for browsing IEEE 2030.5 resources:
- /fsa - Function Set Assignments
- /derc - DER Control
- /dderc - Default DER Control  
- /derp - DER Program
- /edev - End Device
- /dcap - Device Capability
- /der - DER
- /ders - DER Status
- /dera - DER Availability
- /derg - DER Settings
- /dercap - DER Capability
- /mup - Mirror Usage Point
- /mr - Meter Reading
- /sub - Subscription
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
import xml.dom.minidom

from bms_2030_5_client.runtime_config import RuntimeConfig, ProfileConfig

logger = logging.getLogger(__name__)


# ============================================
# IEEE 2030.5 Resource Definitions
# ============================================

@dataclass
class Sep2Resource:
    """IEEE 2030.5 resource definition."""
    id: str
    name: str
    path: str
    description: str
    supports_list: bool = True
    parent_resource: Optional[str] = None


# All browseable IEEE 2030.5 resources
SEP2_RESOURCES: Dict[str, Sep2Resource] = {
    "dcap": Sep2Resource(
        id="dcap",
        name="Device Capability",
        path="/dcap",
        description="根資源，包含所有功能集連結",
        supports_list=False,
    ),
    "edev": Sep2Resource(
        id="edev",
        name="End Device",
        path="/edev",
        description="終端設備列表",
    ),
    "fsa": Sep2Resource(
        id="fsa",
        name="Function Set Assignments",
        path="/fsa",
        description="功能集分配（FSA）",
    ),
    "der": Sep2Resource(
        id="der",
        name="DER",
        path="/der",
        description="分散式能源資源",
    ),
    "derg": Sep2Resource(
        id="derg",
        name="DER Settings",
        path="/derg",
        description="DER 設定參數",
        parent_resource="der",
    ),
    "dercap": Sep2Resource(
        id="dercap",
        name="DER Capability",
        path="/dercap",
        description="DER 設備能力",
        parent_resource="der",
    ),
    "ders": Sep2Resource(
        id="ders",
        name="DER Status",
        path="/ders",
        description="DER 狀態",
        parent_resource="der",
    ),
    "dera": Sep2Resource(
        id="dera",
        name="DER Availability",
        path="/dera",
        description="DER 可用性",
        parent_resource="der",
    ),
    "derp": Sep2Resource(
        id="derp",
        name="DER Program",
        path="/derp",
        description="DER 控制程序",
    ),
    "derc": Sep2Resource(
        id="derc",
        name="DER Control",
        path="/derc",
        description="DER 控制事件",
        parent_resource="derp",
    ),
    "dderc": Sep2Resource(
        id="dderc",
        name="Default DER Control",
        path="/dderc",
        description="預設 DER 控制",
        parent_resource="derp",
    ),
    "mup": Sep2Resource(
        id="mup",
        name="Mirror Usage Point",
        path="/mup",
        description="用戶端計量點",
    ),
    "mr": Sep2Resource(
        id="mr",
        name="Meter Reading",
        path="/mr",
        description="計量讀數",
        parent_resource="mup",
    ),
    "sub": Sep2Resource(
        id="sub",
        name="Subscription",
        path="/sub",
        description="訂閱列表",
    ),
}


# ============================================
# Resource Browser
# ============================================

class ResourceBrowser:
    """
    Browses IEEE 2030.5 resources from server.
    
    Uses the core SepClient for HTTP communication.
    """
    
    def __init__(self, config: RuntimeConfig):
        """
        Initialize browser.
        
        Args:
            config: Runtime configuration
        """
        self.config = config
        self._client = None
    
    def _get_profile(self, profile_name: Optional[str] = None) -> Optional[ProfileConfig]:
        """Get profile by name or first available."""
        if profile_name:
            for p in self.config.profiles:
                if p.name == profile_name:
                    return p
        # Return first profile
        return self.config.profiles[0] if self.config.profiles else None
    
    async def _get_client(self, profile: ProfileConfig):
        """Get or create SEP client for the profile."""
        # Lazy import to avoid circular dependency
        from bms_2030_5_client.core import SepClient
        
        if self._client is None:
            self._client = SepClient(profile)
        return self._client
    
    async def fetch_resource(
        self,
        path: str,
        profile_name: Optional[str] = None,
    ) -> Tuple[int, str, str, float]:
        """
        Fetch a resource from the IEEE 2030.5 server.
        
        Args:
            path: Resource path (e.g., "/dcap", "/edev/1")
            profile_name: Profile to use (optional)
            
        Returns:
            Tuple of (status_code, body, formatted_xml, latency_ms)
        """
        profile = self._get_profile(profile_name)
        if not profile:
            raise ValueError("No profile configured")
        
        client = await self._get_client(profile)
        
        try:
            async with client:
                response = await client.get(path)
                
                # Format XML for display
                formatted = self._format_xml(response.body)
                
                return (response.status_code, response.body, formatted, response.latency_ms)
                
        except Exception as e:
            logger.error(f"Failed to fetch {path}: {e}")
            raise
    
    async def fetch_and_follow_links(
        self,
        path: str,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch resource and extract links for navigation.
        
        Args:
            path: Resource path
            profile_name: Profile to use
            
        Returns:
            Dict with status, body, links, parsed_data
        """
        status, body, formatted, latency = await self.fetch_resource(path, profile_name)
        
        links = self._extract_links(body)
        parsed = self._parse_resource(body)
        
        return {
            "status_code": status,
            "body": body,
            "formatted": formatted,
            "latency_ms": latency,
            "links": links,
            "parsed": parsed,
        }
    
    def _format_xml(self, xml_str: str) -> str:
        """Format XML for display."""
        try:
            # Parse and re-format
            dom = xml.dom.minidom.parseString(xml_str.encode("utf-8"))
            return dom.toprettyxml(indent="  ")
        except Exception:
            return xml_str
    
    def _extract_links(self, xml_str: str) -> List[Dict[str, str]]:
        """Extract href links from XML resource."""
        links = []
        
        try:
            # Remove namespace for easier parsing
            clean_xml = self._strip_namespace(xml_str)
            root = ET.fromstring(clean_xml)
            
            # Find all elements with href attribute
            for elem in root.iter():
                href = elem.get("href")
                if href:
                    links.append({
                        "tag": elem.tag,
                        "href": href,
                        "text": elem.text or "",
                    })
                
                # Also check for xxxLink elements
                if "Link" in elem.tag and elem.text:
                    links.append({
                        "tag": elem.tag,
                        "href": elem.text,
                        "text": "",
                    })
        
        except Exception as e:
            logger.warning(f"Failed to extract links: {e}")
        
        return links
    
    def _parse_resource(self, xml_str: str) -> Dict[str, Any]:
        """Parse XML into a simple dictionary."""
        result = {}
        
        try:
            clean_xml = self._strip_namespace(xml_str)
            root = ET.fromstring(clean_xml)
            
            result["_type"] = root.tag
            result["_attributes"] = dict(root.attrib)
            
            for child in root:
                tag = child.tag
                if len(child) > 0:
                    # Has children, recurse
                    result[tag] = self._element_to_dict(child)
                else:
                    result[tag] = child.text or ""
        
        except Exception as e:
            logger.warning(f"Failed to parse resource: {e}")
            result["_error"] = str(e)
        
        return result
    
    def _element_to_dict(self, elem: ET.Element) -> Dict[str, Any]:
        """Convert XML element to dictionary."""
        result = {}
        result["_attributes"] = dict(elem.attrib)
        
        for child in elem:
            if len(child) > 0:
                result[child.tag] = self._element_to_dict(child)
            else:
                result[child.tag] = child.text or ""
        
        return result
    
    def _strip_namespace(self, xml_str: str) -> str:
        """Remove XML namespace for easier parsing."""
        import re
        # Remove xmlns declarations
        clean = re.sub(r'\s+xmlns[^"]*"[^"]*"', '', xml_str)
        # Remove namespace prefixes
        clean = re.sub(r'<(\w+):', '<', clean)
        clean = re.sub(r'</(\w+):', '</', clean)
        return clean
    
    async def close(self) -> None:
        """Close client connections."""
        if self._client:
            # Client uses async context manager, nothing to explicitly close
            self._client = None


# ============================================
# Meter (MirrorUsagePoint) Manager
# ============================================

@dataclass
class MeterConfig:
    """Configuration for a new meter (MirrorUsagePoint)."""
    description: str
    device_category: int = 7  # Battery storage
    readings: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.readings is None:
            self.readings = []


class MeterManager:
    """
    Manages MirrorUsagePoint creation and updates.
    """
    
    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._created_meters: Dict[str, str] = {}  # mRID -> href
    
    def _get_profile(self, profile_name: Optional[str] = None) -> Optional[ProfileConfig]:
        """Get profile by name or first available."""
        if profile_name:
            for p in self.config.profiles:
                if p.name == profile_name:
                    return p
        return self.config.profiles[0] if self.config.profiles else None
    
    async def create_meter(
        self,
        meter_config: MeterConfig,
        profile_name: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Create a new MirrorUsagePoint (meter).
        
        Args:
            meter_config: Meter configuration
            profile_name: Profile to use
            
        Returns:
            Tuple of (success, message, href)
        """
        from bms_2030_5_client.core import SepClient
        from bms_2030_5_client.models import MirrorUsagePoint
        
        profile = self._get_profile(profile_name)
        if not profile:
            return (False, "No profile configured", None)
        
        # Build MirrorUsagePoint XML  (UUID 96-bit + IANA PEN 32-bit)
        import uuid
        from bms_2030_5_client.models.ieee2030_5_models import DEFAULT_IANA_PEN
        mrid = uuid.uuid4().hex[:24].upper() + f"{DEFAULT_IANA_PEN:08X}"
        
        mup_xml = self._build_mup_xml(
            mrid=mrid,
            description=meter_config.description,
            device_category=meter_config.device_category,
        )
        
        client = SepClient(profile)
        
        try:
            async with client:
                response = await client.post("/mup", mup_xml)
                
                if response.is_created:
                    location = response.headers.get("location", "")
                    self._created_meters[mrid] = location
                    return (True, f"Meter created: {location}", location)
                else:
                    return (False, f"Failed: HTTP {response.status_code}", None)
                    
        except Exception as e:
            logger.error(f"Failed to create meter: {e}")
            return (False, str(e), None)
    
    def _build_mup_xml(
        self,
        mrid: str,
        description: str,
        device_category: int,
    ) -> str:
        """Build MirrorUsagePoint XML."""
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<MirrorUsagePoint xmlns="urn:ieee:std:2030.5:ns">
    <mRID>{mrid}</mRID>
    <description>{description}</description>
    <roleFlags>00</roleFlags>
    <serviceCategoryKind>0</serviceCategoryKind>
    <status>0</status>
    <deviceLFDI>{{lfdi}}</deviceLFDI>
</MirrorUsagePoint>'''
        return xml
    
    async def add_meter_reading(
        self,
        mup_href: str,
        reading_type: str,
        value: int,
        multiplier: int = 0,
        profile_name: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Add a meter reading to an existing MirrorUsagePoint.
        
        Args:
            mup_href: MirrorUsagePoint href
            reading_type: Type of reading (e.g., "soc", "power")
            value: Reading value
            multiplier: Power of 10 multiplier
            profile_name: Profile to use
            
        Returns:
            Tuple of (success, message)
        """
        from bms_2030_5_client.core import SepClient
        
        profile = self._get_profile(profile_name)
        if not profile:
            return (False, "No profile configured")
        
        # Build MirrorMeterReading XML
        mmr_xml = self._build_mmr_xml(reading_type, value, multiplier)
        
        client = SepClient(profile)
        
        try:
            async with client:
                # POST to mup_href/mmr
                mmr_path = f"{mup_href}/mmr"
                response = await client.post(mmr_path, mmr_xml)
                
                if response.is_created or response.is_success:
                    return (True, f"Reading added: {reading_type}={value}")
                else:
                    return (False, f"Failed: HTTP {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Failed to add meter reading: {e}")
            return (False, str(e))
    
    def _build_mmr_xml(
        self,
        reading_type: str,
        value: int,
        multiplier: int = 0,
    ) -> str:
        """Build MirrorMeterReading XML."""
        import uuid
        import time
        
        mrid = uuid.uuid4().hex[:32].upper()
        now = int(time.time())
        
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<MirrorMeterReading xmlns="urn:ieee:std:2030.5:ns">
    <mRID>{mrid}</mRID>
    <description>{reading_type}</description>
    <Reading>
        <timePeriod>
            <duration>0</duration>
            <start>{now}</start>
        </timePeriod>
        <value>{value}</value>
    </Reading>
    <ReadingType>
        <powerOfTenMultiplier>{multiplier}</powerOfTenMultiplier>
    </ReadingType>
</MirrorMeterReading>'''
        return xml
    
    @property
    def created_meters(self) -> Dict[str, str]:
        """Get map of created meter mRIDs to hrefs."""
        return dict(self._created_meters)
