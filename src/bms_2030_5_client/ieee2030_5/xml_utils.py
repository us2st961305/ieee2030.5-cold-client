"""
XML serialization utilities for IEEE 2030.5.
"""

import logging
import xml.etree.ElementTree as ET
from enum import Enum
from typing import Any, Type, TypeVar, get_type_hints, get_origin, get_args
from dataclasses import fields, is_dataclass

logger = logging.getLogger(__name__)

T = TypeVar("T")

# IEEE 2030.5 / Smart Energy Profile namespace
IEEE2030_5_NS = "urn:ieee:std:2030.5:ns"
NS_MAP = {"sep": IEEE2030_5_NS}


def _strip_namespace(tag: str) -> str:
    """Remove namespace from XML tag."""
    if tag.startswith("{"):
        return tag.split("}")[1]
    return tag


def _get_link_class():
    """Get the Link class for type checking."""
    from bms_2030_5_client.models import Link
    return Link


def _parse_element_to_dataclass(element: ET.Element, cls: Type[T]) -> T:
    """
    Parse XML element to dataclass instance
    
    Args:
        element: XML Element
        cls: Target dataclass type
        
    Returns:
        Parsed dataclass instance
    """
    if not is_dataclass(cls):
        raise ValueError(f"Expected dataclass type, got {cls}")
    
    kwargs = {}
    type_hints = get_type_hints(cls)
    Link = _get_link_class()
    
    # Initialize list fields
    for field_name, hint in type_hints.items():
        origin = get_origin(hint)
        if origin is list:
            kwargs[field_name] = []
        # Parse attributes (href, pollRate, all, etc.)
    for attr_name, attr_value in element.attrib.items():
        attr_name = _strip_namespace(attr_name)
        if attr_name in type_hints:
            hint = type_hints[attr_name]
            # Handle Optional types
            origin = get_origin(hint)
            if origin is type(None) or hint is type(None):
                continue
            
            actual_type = hint
            if origin:
                args = get_args(hint)
                if args:
                    actual_type = args[0] if args[0] is not type(None) else (args[1] if len(args) > 1 else str)
            
            # Convert value to appropriate type
            if actual_type == int:
                kwargs[attr_name] = int(attr_value)
            elif actual_type == float:
                kwargs[attr_name] = float(attr_value)
            elif actual_type == bool:
                kwargs[attr_name] = attr_value.lower() in ('true', '1', 'yes')
            else:
                kwargs[attr_name] = attr_value
    
    # Parse child elements
    for child in element:
        child_tag = _strip_namespace(child.tag)
        
        if child_tag in type_hints:
            hint = type_hints[child_tag]
            origin = get_origin(hint)
            
            # Check if this field is a List type
            is_list_field = origin is list
            
            actual_type = hint
            if origin:
                args = get_args(hint)
                if args:
                    actual_type = args[0] if args[0] is not type(None) else (args[1] if len(args) > 1 else str)
            
            # Check if it's a Link type (by name pattern)
            if child_tag.endswith('Link'):
                # Create Link object from attributes
                link_kwargs = {}
                for attr_name, attr_value in child.attrib.items():
                    attr_name = _strip_namespace(attr_name)
                    if attr_name == 'href':
                        link_kwargs['href'] = attr_value
                    elif attr_name == 'all':
                        link_kwargs['all'] = int(attr_value)
                kwargs[child_tag] = Link(**link_kwargs)
            elif origin is list:
                # Handle List[T] types - collect all matching elements
                if child_tag not in kwargs:
                    kwargs[child_tag] = []
                if is_dataclass(actual_type):
                    kwargs[child_tag].append(_parse_element_to_dataclass(child, actual_type))
                elif child.text:
                    if actual_type == int:
                        kwargs[child_tag].append(int(child.text))
                    elif actual_type == float:
                        kwargs[child_tag].append(float(child.text))
                    elif actual_type == bool:
                        kwargs[child_tag].append(child.text.lower() in ('true', '1', 'yes'))
                    else:
                        kwargs[child_tag].append(child.text)
            elif is_dataclass(actual_type):
                parsed_value = _parse_element_to_dataclass(child, actual_type)
                if is_list_field:
                    kwargs[child_tag].append(parsed_value)
                else:
                    kwargs[child_tag] = parsed_value
            elif child.text:
                if actual_type == int:
                    kwargs[child_tag] = int(child.text)
                elif actual_type == float:
                    kwargs[child_tag] = float(child.text)
                elif actual_type == bool:
                    kwargs[child_tag] = child.text.lower() in ('true', '1', 'yes')
                else:
                    kwargs[child_tag] = child.text
    
    logger.debug(f"Creating {cls.__name__} with kwargs: {kwargs}")
    return cls(**kwargs)


def xml_to_dataclass(xml_str: str, cls: Type[T]) -> T:
    """
    Parse XML string to dataclass.
    
    Args:
        xml_str: XML string
        cls: Target dataclass type
        
    Returns:
        Parsed dataclass instance
    """
    logger.debug(f"Parsing XML to {cls.__name__}")
    logger.debug(f"XML content:\n{xml_str}")
    
    try:
        root = ET.fromstring(xml_str)
        result = _parse_element_to_dataclass(root, cls)
        
        logger.debug(f"Parse result: {result}")
        if is_dataclass(result):
            for f in fields(result):
                value = getattr(result, f.name)
                logger.debug(f"  {f.name}: {value}")
        
        return result
    except Exception as e:
        logger.error(f"XML parsing error: {type(e).__name__}: {e}")
        raise


def dataclass_to_xml(obj: Any, root_tag: str = None) -> str:
    """
    Convert dataclass to IEEE 2030.5 XML string.
    
    Args:
        obj: Dataclass instance
        root_tag: Optional root element tag name
        
    Returns:
        XML string
    """
    if not is_dataclass(obj):
        raise ValueError(f"Expected dataclass, got {type(obj)}")
    
    tag = root_tag or obj.__class__.__name__
    root = ET.Element(tag, xmlns=IEEE2030_5_NS)
    
    _dataclass_to_element(obj, root)
    
    return ET.tostring(root, encoding='unicode')


def _dataclass_to_element(obj: Any, element: ET.Element) -> None:
    """
    Convert dataclass fields to XML element.
    """
    Link = _get_link_class()
    
    for f in fields(obj):
        value = getattr(obj, f.name)
        if value is None:
            continue
        
        # Handle special field names
        field_name = f.name
        if field_name == 'type_':
            field_name = 'type'
        
        # Convert Enum to its value
        if isinstance(value, Enum):
            value = value.value
        
        if isinstance(value, (int, float, str, bool)):
            # Simple types as attributes or child elements
            if field_name in ('href', 'pollRate', 'all'):
                element.set(field_name, str(value))
            else:
                child = ET.SubElement(element, field_name)
                child.text = str(value)
        elif isinstance(value, bytes):
            # Bytes (e.g., lFDI, mRID) as hex string
            child = ET.SubElement(element, field_name)
            child.text = value.hex().upper()
        elif isinstance(value, Link):
            # Link objects
            child = ET.SubElement(element, field_name)
            if value.href:
                child.set('href', value.href)
            if value.all is not None:
                child.set('all', str(value.all))
        elif is_dataclass(value):
            child = ET.SubElement(element, field_name)
            _dataclass_to_element(value, child)
        elif isinstance(value, list):
            for item in value:
                if is_dataclass(item):
                    child = ET.SubElement(element, item.__class__.__name__)
                    _dataclass_to_element(item, child)


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
