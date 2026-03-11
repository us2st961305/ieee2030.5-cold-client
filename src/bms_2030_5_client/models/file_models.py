"""
IEEE 2030.5-2023 File Function Set.

This module provides the complete File Function Set implementation including:
- File: Container for file metadata
- FileList: Collection of file resources
- FileStatus: Status tracking for file downloads/uploads
- FileType: File type enumeration

Reference: IEEE Std 2030.5-2023
- Section 10.11: File Function Set
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List
from dataclasses_json import dataclass_json


# =============================================================================
# File Type Enumeration
# =============================================================================

class FileType(IntEnum):
    """
    File Type enumeration.
    
    Reference: IEEE Std 2030.5-2023
    
    Defines the type of file content.
    """
    # 0: Software image
    SOFTWARE_IMAGE = 0
    
    # 1: Configuration file
    CONFIGURATION = 1
    
    # 2: Log file
    LOG_FILE = 2
    
    # 3: Text file (general purpose)
    TEXT_FILE = 3
    
    # 4: Binary file (general purpose)
    BINARY_FILE = 4
    
    # 5: XML file
    XML_FILE = 5
    
    # 6: Security credentials/certificates
    SECURITY_CREDENTIALS = 6
    
    # 7-255: Reserved / Manufacturer specific


# =============================================================================
# File Status Enumeration
# =============================================================================

class FileStatusType(IntEnum):
    """
    File Status enumeration.
    
    Indicates the current status of a file download or upload operation.
    """
    # 0: Not started
    NOT_STARTED = 0
    
    # 1: Download/upload in progress
    IN_PROGRESS = 1
    
    # 2: Download/upload completed successfully
    COMPLETED = 2
    
    # 3: Download/upload failed
    FAILED = 3
    
    # 4: Download/upload cancelled
    CANCELLED = 4
    
    # 5: File verification in progress
    VERIFYING = 5
    
    # 6: File verified successfully
    VERIFIED = 6
    
    # 7: File verification failed
    VERIFICATION_FAILED = 7
    
    # 8: File installed/applied successfully
    INSTALLED = 8
    
    # 9: File installation/application failed
    INSTALLATION_FAILED = 9


# =============================================================================
# File Activation Status
# =============================================================================

class ActivationStatusType(IntEnum):
    """
    Activation status for firmware/software updates.
    """
    # 0: Not activated
    NOT_ACTIVATED = 0
    
    # 1: Activation scheduled
    SCHEDULED = 1
    
    # 2: Activation in progress
    IN_PROGRESS = 2
    
    # 3: Activated successfully
    ACTIVATED = 3
    
    # 4: Activation failed
    FAILED = 4
    
    # 5: Rollback in progress
    ROLLBACK_IN_PROGRESS = 5
    
    # 6: Rollback completed
    ROLLBACK_COMPLETED = 6


# =============================================================================
# File Status
# =============================================================================

@dataclass_json
@dataclass
class FileStatus:
    """
    File Status resource.
    
    Reference: IEEE Std 2030.5-2023
    
    Tracks the status of a file download/upload operation.
    
    Attributes:
        href: URI of this resource
        loadPercent: Download/upload progress (0-100)
        nextRequestAttempt: Time of next retry attempt (POSIX seconds)
        status: Current file status
        request503Count: Number of 503 responses received
        requestFailCount: Number of failed requests
    """
    href: Optional[str] = None
    loadPercent: int = 0
    nextRequestAttempt: Optional[int] = None
    status: FileStatusType = FileStatusType.NOT_STARTED
    request503Count: int = 0
    requestFailCount: int = 0
    
    # Activation status (for firmware updates)
    activationStatus: Optional[ActivationStatusType] = None
    activationTime: Optional[int] = None  # Scheduled activation time
    
    def is_in_progress(self) -> bool:
        """Check if download/upload is in progress."""
        return self.status == FileStatusType.IN_PROGRESS
    
    def is_complete(self) -> bool:
        """Check if file operation completed successfully."""
        return self.status in (FileStatusType.COMPLETED, 
                               FileStatusType.VERIFIED,
                               FileStatusType.INSTALLED)
    
    def is_failed(self) -> bool:
        """Check if file operation failed."""
        return self.status in (FileStatusType.FAILED,
                               FileStatusType.VERIFICATION_FAILED,
                               FileStatusType.INSTALLATION_FAILED)


@dataclass_json
@dataclass
class FileStatusList:
    """List of FileStatus resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    FileStatus: List[FileStatus] = field(default_factory=list)


# =============================================================================
# File Resource
# =============================================================================

@dataclass_json
@dataclass
class File:
    """
    File resource.
    
    Reference: IEEE Std 2030.5-2023 Section 10.11
    
    Represents a file that can be downloaded or referenced.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier (UInt128 as hex)
        description: Human-readable description
        version: Version number for tracking updates
        
        # File identification
        fileURI: URI from which to download the file
        localPath: Local path where file is stored (client-side)
        
        # File metadata
        type_: Type of file (software, config, log, etc.)
        size: File size in bytes
        
        # Timing
        activateTime: When the file should be activated (POSIX seconds)
        
        # Security
        signature: Digital signature for verification
        fingerprint: SHA-256 hash of file content
        
        # Status link
        FileStatusLink: URI to file status resource
    """
    # Resource identification
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # File location
    fileURI: Optional[str] = None
    localPath: Optional[str] = None
    
    # File metadata
    type_: FileType = FileType.BINARY_FILE
    size: Optional[int] = None  # Bytes
    mimeType: Optional[str] = None
    
    # Timing
    activateTime: Optional[int] = None  # POSIX seconds
    
    # Security/verification
    signature: Optional[str] = None      # Digital signature
    fingerprint: Optional[str] = None    # SHA-256 hash (hex string)
    
    # Link to status
    FileStatusLink: Optional[dict] = None
    
    def get_file_type_name(self) -> str:
        """Get human-readable file type name."""
        return self.type_.name
    
    def get_size_human(self) -> str:
        """Get human-readable file size."""
        if self.size is None:
            return "Unknown"
        
        if self.size < 1024:
            return f"{self.size} B"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        elif self.size < 1024 * 1024 * 1024:
            return f"{self.size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.size / (1024 * 1024 * 1024):.2f} GB"
    
    def verify_fingerprint(self, calculated_hash: str) -> bool:
        """
        Verify file fingerprint matches calculated hash.
        
        Args:
            calculated_hash: SHA-256 hash of downloaded content
            
        Returns:
            True if fingerprints match
        """
        if self.fingerprint is None:
            return True  # No fingerprint to verify
        return self.fingerprint.lower() == calculated_hash.lower()


@dataclass_json
@dataclass
class FileList:
    """List of File resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    File: List[File] = field(default_factory=list)
    
    def get_by_type(self, file_type: FileType) -> List[File]:
        """Get all files of a specific type."""
        return [f for f in self.File if f.type_ == file_type]
    
    def get_software_images(self) -> List[File]:
        """Get all software image files."""
        return self.get_by_type(FileType.SOFTWARE_IMAGE)
    
    def get_configuration_files(self) -> List[File]:
        """Get all configuration files."""
        return self.get_by_type(FileType.CONFIGURATION)


# =============================================================================
# File Download Progress Tracking
# =============================================================================

@dataclass_json
@dataclass
class FileDownloadProgress:
    """
    Client-side tracking of file download progress.
    
    Not part of IEEE 2030.5 spec, but useful for client implementation.
    """
    file_mRID: str = ""
    file_uri: str = ""
    total_size: int = 0
    downloaded_size: int = 0
    status: FileStatusType = FileStatusType.NOT_STARTED
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def get_progress_percent(self) -> int:
        """Get download progress as percentage."""
        if self.total_size == 0:
            return 0
        return min(100, int((self.downloaded_size / self.total_size) * 100))
    
    def is_resumable(self) -> bool:
        """Check if download can be resumed."""
        return (self.status == FileStatusType.FAILED and 
                self.retry_count < self.max_retries)
    
    def get_download_rate(self, current_time: int) -> Optional[float]:
        """
        Get download rate in bytes per second.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            Bytes per second, or None if not calculable
        """
        if self.start_time is None or self.downloaded_size == 0:
            return None
        
        elapsed = current_time - self.start_time
        if elapsed <= 0:
            return None
        
        return self.downloaded_size / elapsed
    
    def estimate_remaining_time(self, current_time: int) -> Optional[int]:
        """
        Estimate remaining download time in seconds.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            Estimated seconds remaining, or None if not calculable
        """
        rate = self.get_download_rate(current_time)
        if rate is None or rate == 0:
            return None
        
        remaining_bytes = self.total_size - self.downloaded_size
        return int(remaining_bytes / rate)


# =============================================================================
# Firmware Update Request
# =============================================================================

@dataclass_json
@dataclass
class FirmwareUpdateRequest:
    """
    Request to update firmware/software.
    
    Used internally by client to track firmware update operations.
    """
    file: File = field(default_factory=File)
    status: ActivationStatusType = ActivationStatusType.NOT_ACTIVATED
    scheduled_time: Optional[int] = None
    require_reboot: bool = False
    rollback_file: Optional[File] = None
    
    def should_activate_now(self, current_time: int) -> bool:
        """Check if firmware should be activated now."""
        if self.scheduled_time is None:
            return False
        return current_time >= self.scheduled_time


# =============================================================================
# Helper Functions
# =============================================================================

def create_file_resource(
    mRID: str,
    file_uri: str,
    file_type: FileType,
    size: Optional[int] = None,
    description: Optional[str] = None,
    fingerprint: Optional[str] = None,
    activate_time: Optional[int] = None,
    mime_type: Optional[str] = None,
) -> File:
    """
    Create a File resource with common parameters.
    
    Args:
        mRID: Unique identifier for the file
        file_uri: URI to download the file
        file_type: Type of file
        size: File size in bytes
        description: Human-readable description
        fingerprint: SHA-256 hash for verification
        activate_time: When to activate (for firmware)
        mime_type: MIME type of file content
        
    Returns:
        Configured File resource
    """
    return File(
        mRID=mRID,
        fileURI=file_uri,
        type_=file_type,
        size=size,
        description=description or f"File: {mRID}",
        fingerprint=fingerprint,
        activateTime=activate_time,
        mimeType=mime_type,
    )


def create_firmware_image(
    mRID: str,
    file_uri: str,
    size: int,
    fingerprint: str,
    version: str,
    activate_time: Optional[int] = None,
) -> File:
    """
    Create a firmware/software image file resource.
    
    Args:
        mRID: Unique identifier for the firmware
        file_uri: URI to download the firmware
        size: Firmware size in bytes
        fingerprint: SHA-256 hash for verification
        version: Firmware version string
        activate_time: When to activate firmware
        
    Returns:
        Configured File resource for firmware
    """
    return File(
        mRID=mRID,
        fileURI=file_uri,
        type_=FileType.SOFTWARE_IMAGE,
        size=size,
        description=f"Firmware v{version}",
        fingerprint=fingerprint,
        activateTime=activate_time,
        mimeType="application/octet-stream",
        version=1,
    )


def create_config_file(
    mRID: str,
    file_uri: str,
    size: Optional[int] = None,
    fingerprint: Optional[str] = None,
    description: str = "Configuration File",
) -> File:
    """
    Create a configuration file resource.
    
    Args:
        mRID: Unique identifier for the config
        file_uri: URI to download the config
        size: File size in bytes
        fingerprint: SHA-256 hash for verification
        description: Human-readable description
        
    Returns:
        Configured File resource for configuration
    """
    return File(
        mRID=mRID,
        fileURI=file_uri,
        type_=FileType.CONFIGURATION,
        size=size,
        description=description,
        fingerprint=fingerprint,
        mimeType="application/xml",
    )


def get_mime_type_for_file_type(file_type: FileType) -> str:
    """
    Get default MIME type for a file type.
    
    Args:
        file_type: FileType enum value
        
    Returns:
        Appropriate MIME type string
    """
    mime_types = {
        FileType.SOFTWARE_IMAGE: "application/octet-stream",
        FileType.CONFIGURATION: "application/xml",
        FileType.LOG_FILE: "text/plain",
        FileType.TEXT_FILE: "text/plain",
        FileType.BINARY_FILE: "application/octet-stream",
        FileType.XML_FILE: "application/xml",
        FileType.SECURITY_CREDENTIALS: "application/x-pem-file",
    }
    return mime_types.get(file_type, "application/octet-stream")
