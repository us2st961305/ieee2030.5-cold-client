"""
XML serialization utilities for IEEE 2030.5.
"""

from typing import Any, Type, TypeVar
from dataclasses import fields, is_dataclass

from xsdata.formats.dataclass.context import XmlContext
from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

T = TypeVar("T")

# IEEE 2030.5 / Smart Energy Profile namespace
NS_MAP = {None: "urn:ieee:std:2030.5:ns"}

# XSData configuration
_context = XmlContext()
_parser = XmlParser(context=_context)
_serializer_config = SerializerConfig(
    xml_declaration=False,
    pretty_print=True,
)
_serializer = XmlSerializer(config=_serializer_config)


def dataclass_to_xml(obj: Any) -> str:
    """
    Convert dataclass to IEEE 2030.5 XML string.
    
    Args:
        obj: Dataclass instance
        
    Returns:
        XML string
    """
    if not is_dataclass(obj):
        raise ValueError(f"Expected dataclass, got {type(obj)}")
    
    return _serializer.render(obj, ns_map=NS_MAP)


def xml_to_dataclass(xml_str: str, cls: Type[T]) -> T:
    """
    Parse XML string to dataclass.
    
    Args:
        xml_str: XML string
        cls: Target dataclass type
        
    Returns:
        Parsed dataclass instance
    """
    return _parser.from_string(xml_str, cls)


def dataclass_to_dict(obj: Any) -> dict:
    """
    Convert dataclass to dictionary.
    
    Args:
        obj: Dataclass instance
        
    Returns:
        Dictionary representation
    """
    if not is_dataclass(obj):
        return obj
    
    result = {}
    for f in fields(obj):
        value = getattr(obj, f.name)
        if is_dataclass(value):
            result[f.name] = dataclass_to_dict(value)
        elif isinstance(value, list):
            result[f.name] = [
                dataclass_to_dict(item) if is_dataclass(item) else item
                for item in value
            ]
        else:
            result[f.name] = value
    
    return result
