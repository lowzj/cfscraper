import asyncio
import csv
import json
import logging
import gzip
import zipfile
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, IO
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from io import StringIO, BytesIO
import xml.etree.ElementTree as ET
from xml.dom import minidom
import tempfile
import os

logger = logging.getLogger(__name__)


class ExportFormat(str, Enum):
    """Supported export formats"""
    JSON = "json"
    CSV = "csv"
    XML = "xml"
    JSONL = "jsonl"  # JSON Lines format


class CompressionType(str, Enum):
    """Supported compression types"""
    NONE = "none"
    GZIP = "gzip"
    ZIP = "zip"


@dataclass
class ExportConfig:
    """Configuration for data export"""
    format: ExportFormat = ExportFormat.JSON
    compression: CompressionType = CompressionType.NONE
    include_metadata: bool = True
    pretty_print: bool = True
    chunk_size: int = 1000
    max_file_size_mb: int = 100
    
    # CSV specific options
    csv_delimiter: str = ","
    csv_quote_char: str = '"'
    csv_include_headers: bool = True
    
    # XML specific options
    xml_root_element: str = "data"
    xml_item_element: str = "item"
    
    # JSON specific options
    json_indent: int = 2


class DataTransformer:
    """Handles data transformation and cleaning"""
    
    def __init__(self):
        self._lock = asyncio.Lock()
    
    async def clean_data(self, data: Any) -> Any:
        """Clean and normalize data"""
        if isinstance(data, dict):
            return await self._clean_dict(data)
        elif isinstance(data, list):
            return await self._clean_list(data)
        elif isinstance(data, str):
            return self._clean_string(data)
        else:
            return data
    
    async def _clean_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean dictionary data"""
        cleaned = {}
        for key, value in data.items():
            # Clean key
            clean_key = self._clean_string(str(key))
            # Clean value
            cleaned[clean_key] = await self.clean_data(value)
        return cleaned
    
    async def _clean_list(self, data: List[Any]) -> List[Any]:
        """Clean list data"""
        return [await self.clean_data(item) for item in data]
    
    def _clean_string(self, data: str) -> str:
        """Clean string data"""
        if not isinstance(data, str):
            return str(data)
        
        # Remove null bytes and control characters
        cleaned = data.replace('\x00', '').replace('\r', '').strip()
        
        # Normalize whitespace
        cleaned = ' '.join(cleaned.split())
        
        return cleaned
    
    async def flatten_data(self, data: Dict[str, Any], prefix: str = "", separator: str = ".") -> Dict[str, Any]:
        """Flatten nested dictionary"""
        flattened = {}
        
        for key, value in data.items():
            new_key = f"{prefix}{separator}{key}" if prefix else key
            
            if isinstance(value, dict):
                nested = await self.flatten_data(value, new_key, separator)
                flattened.update(nested)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # Handle list of dictionaries
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        nested = await self.flatten_data(item, f"{new_key}[{i}]", separator)
                        flattened.update(nested)
                    else:
                        flattened[f"{new_key}[{i}]"] = item
            else:
                flattened[new_key] = value
        
        return flattened


class JSONExporter:
    """Handles JSON export functionality"""
    
    def __init__(self, config: ExportConfig):
        self.config = config
        self.transformer = DataTransformer()
    
    async def export_data(self, data: List[Dict[str, Any]], output_file: IO) -> int:
        """Export data to JSON format"""
        try:
            # Clean data if needed
            cleaned_data = []
            for item in data:
                cleaned_item = await self.transformer.clean_data(item)
                cleaned_data.append(cleaned_item)
            
            # Add metadata if requested
            export_data = {
                "data": cleaned_data,
                "metadata": {
                    "export_timestamp": datetime.now().isoformat(),
                    "total_records": len(cleaned_data),
                    "format": "json"
                } if self.config.include_metadata else None
            }
            
            if not self.config.include_metadata:
                export_data = cleaned_data
            
            # Write JSON
            json_str = json.dumps(
                export_data,
                indent=self.config.json_indent if self.config.pretty_print else None,
                ensure_ascii=False,
                default=str
            )
            
            output_file.write(json_str)
            return len(json_str)
            
        except Exception as e:
            logger.error(f"JSON export failed: {str(e)}")
            raise
    
    async def export_streaming(self, data_generator: AsyncGenerator[Dict[str, Any], None], output_file: IO) -> int:
        """Export data using streaming for large datasets"""
        total_bytes = 0
        
        try:
            # Start JSON array
            output_file.write('[\n')
            total_bytes += 2
            
            first_item = True
            async for item in data_generator:
                if not first_item:
                    output_file.write(',\n')
                    total_bytes += 2
                
                cleaned_item = await self.transformer.clean_data(item)
                json_str = json.dumps(cleaned_item, ensure_ascii=False, default=str)
                
                if self.config.pretty_print:
                    json_str = '  ' + json_str
                    total_bytes += 2
                
                output_file.write(json_str)
                total_bytes += len(json_str)
                first_item = False
            
            # Close JSON array
            output_file.write('\n]')
            total_bytes += 2
            
            return total_bytes
            
        except Exception as e:
            logger.error(f"Streaming JSON export failed: {str(e)}")
            raise


class CSVExporter:
    """Handles CSV export functionality"""
    
    def __init__(self, config: ExportConfig):
        self.config = config
        self.transformer = DataTransformer()
    
    async def export_data(self, data: List[Dict[str, Any]], output_file: IO) -> int:
        """Export data to CSV format"""
        if not data:
            return 0
        
        try:
            # Clean and flatten data
            cleaned_data = []
            for item in data:
                cleaned_item = await self.transformer.clean_data(item)
                flattened_item = await self.transformer.flatten_data(cleaned_item)
                cleaned_data.append(flattened_item)
            
            # Get all unique keys for headers
            all_keys = set()
            for item in cleaned_data:
                all_keys.update(item.keys())
            
            headers = sorted(list(all_keys))
            
            # Create CSV writer
            writer = csv.DictWriter(
                output_file,
                fieldnames=headers,
                delimiter=self.config.csv_delimiter,
                quotechar=self.config.csv_quote_char,
                quoting=csv.QUOTE_MINIMAL
            )
            
            total_bytes = 0
            
            # Write headers
            if self.config.csv_include_headers:
                writer.writeheader()
                # Estimate header size
                header_line = self.config.csv_delimiter.join(headers) + '\n'
                total_bytes += len(header_line)
            
            # Write data rows
            for item in cleaned_data:
                # Ensure all keys are present
                row = {key: item.get(key, '') for key in headers}
                writer.writerow(row)
                # Estimate row size
                row_line = self.config.csv_delimiter.join(str(v) for v in row.values()) + '\n'
                total_bytes += len(row_line)
            
            return total_bytes
            
        except Exception as e:
            logger.error(f"CSV export failed: {str(e)}")
            raise
    
    async def export_streaming(self, data_generator: AsyncGenerator[Dict[str, Any], None], output_file: IO) -> int:
        """Export data using streaming for large datasets"""
        total_bytes = 0
        headers_written = False
        writer = None
        all_headers = set()
        
        try:
            # First pass to collect all headers
            temp_data = []
            async for item in data_generator:
                cleaned_item = await self.transformer.clean_data(item)
                flattened_item = await self.transformer.flatten_data(cleaned_item)
                temp_data.append(flattened_item)
                all_headers.update(flattened_item.keys())
            
            headers = sorted(list(all_headers))
            
            # Create CSV writer
            writer = csv.DictWriter(
                output_file,
                fieldnames=headers,
                delimiter=self.config.csv_delimiter,
                quotechar=self.config.csv_quote_char,
                quoting=csv.QUOTE_MINIMAL
            )
            
            # Write headers
            if self.config.csv_include_headers:
                writer.writeheader()
                header_line = self.config.csv_delimiter.join(headers) + '\n'
                total_bytes += len(header_line)
            
            # Write data
            for item in temp_data:
                row = {key: item.get(key, '') for key in headers}
                writer.writerow(row)
                row_line = self.config.csv_delimiter.join(str(v) for v in row.values()) + '\n'
                total_bytes += len(row_line)
            
            return total_bytes
            
        except Exception as e:
            logger.error(f"Streaming CSV export failed: {str(e)}")
            raise


class XMLExporter:
    """Handles XML export functionality"""

    def __init__(self, config: ExportConfig):
        self.config = config
        self.transformer = DataTransformer()

    async def export_data(self, data: List[Dict[str, Any]], output_file: IO) -> int:
        """Export data to XML format"""
        try:
            # Create root element
            root = ET.Element(self.config.xml_root_element)

            # Add metadata if requested
            if self.config.include_metadata:
                metadata = ET.SubElement(root, "metadata")
                ET.SubElement(metadata, "export_timestamp").text = datetime.now().isoformat()
                ET.SubElement(metadata, "total_records").text = str(len(data))
                ET.SubElement(metadata, "format").text = "xml"

            # Add data items
            for item in data:
                cleaned_item = await self.transformer.clean_data(item)
                item_element = ET.SubElement(root, self.config.xml_item_element)
                await self._dict_to_xml(cleaned_item, item_element)

            # Convert to string
            xml_str = ET.tostring(root, encoding='unicode')

            if self.config.pretty_print:
                # Pretty print XML
                dom = minidom.parseString(xml_str)
                xml_str = dom.toprettyxml(indent="  ")
                # Remove empty lines
                xml_str = '\n'.join([line for line in xml_str.split('\n') if line.strip()])

            output_file.write(xml_str)
            return len(xml_str)

        except Exception as e:
            logger.error(f"XML export failed: {str(e)}")
            raise

    async def _dict_to_xml(self, data: Dict[str, Any], parent: ET.Element):
        """Convert dictionary to XML elements"""
        for key, value in data.items():
            # Clean key to be valid XML element name
            clean_key = self._clean_xml_key(key)

            if isinstance(value, dict):
                child = ET.SubElement(parent, clean_key)
                await self._dict_to_xml(value, child)
            elif isinstance(value, list):
                for item in value:
                    child = ET.SubElement(parent, clean_key)
                    if isinstance(item, dict):
                        await self._dict_to_xml(item, child)
                    else:
                        child.text = str(item)
            else:
                child = ET.SubElement(parent, clean_key)
                child.text = str(value) if value is not None else ""

    def _clean_xml_key(self, key: str) -> str:
        """Clean key to be valid XML element name"""
        # Replace invalid characters with underscores
        import re
        clean_key = re.sub(r'[^a-zA-Z0-9_-]', '_', str(key))
        # Ensure it starts with a letter or underscore
        if clean_key and not clean_key[0].isalpha() and clean_key[0] != '_':
            clean_key = f"item_{clean_key}"
        return clean_key or "item"


class CompressionManager:
    """Handles file compression"""

    @staticmethod
    def compress_data(data: bytes, compression_type: CompressionType) -> bytes:
        """Compress data using specified compression type"""
        if compression_type == CompressionType.GZIP:
            return gzip.compress(data)
        elif compression_type == CompressionType.ZIP:
            # Create a ZIP file in memory
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("data.txt", data)
            return zip_buffer.getvalue()
        else:
            return data

    @staticmethod
    def get_file_extension(format_type: ExportFormat, compression_type: CompressionType) -> str:
        """Get appropriate file extension"""
        base_ext = {
            ExportFormat.JSON: ".json",
            ExportFormat.CSV: ".csv",
            ExportFormat.XML: ".xml",
            ExportFormat.JSONL: ".jsonl"
        }.get(format_type, ".txt")

        if compression_type == CompressionType.GZIP:
            return base_ext + ".gz"
        elif compression_type == CompressionType.ZIP:
            return base_ext + ".zip"
        else:
            return base_ext


class DataExportManager:
    """Main manager for data export operations"""

    def __init__(self, config: Optional[ExportConfig] = None):
        self.config = config or ExportConfig()
        self._exporters = {
            ExportFormat.JSON: JSONExporter(self.config),
            ExportFormat.CSV: CSVExporter(self.config),
            ExportFormat.XML: XMLExporter(self.config),
            ExportFormat.JSONL: JSONExporter(self.config)  # JSONL uses JSON exporter
        }

    async def export_data(
        self,
        data: List[Dict[str, Any]],
        output_path: Optional[str] = None,
        format_type: Optional[ExportFormat] = None
    ) -> str:
        """
        Export data to specified format

        Args:
            data: List of dictionaries to export
            output_path: Optional output file path
            format_type: Export format (overrides config)

        Returns:
            Path to exported file
        """
        export_format = format_type or self.config.format

        if export_format not in self._exporters:
            raise ValueError(f"Unsupported export format: {export_format}")

        # Generate output path if not provided
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            extension = CompressionManager.get_file_extension(export_format, self.config.compression)
            output_path = f"export_{timestamp}{extension}"

        try:
            # Export data
            if self.config.compression == CompressionType.NONE:
                # Direct file writing
                with open(output_path, 'w', encoding='utf-8') as f:
                    exporter = self._exporters[export_format]
                    await exporter.export_data(data, f)
            else:
                # Export to memory first, then compress
                with StringIO() as temp_buffer:
                    exporter = self._exporters[export_format]
                    await exporter.export_data(data, temp_buffer)

                    # Get data and compress
                    data_str = temp_buffer.getvalue()
                    data_bytes = data_str.encode('utf-8')
                    compressed_data = CompressionManager.compress_data(data_bytes, self.config.compression)

                    # Write compressed data
                    with open(output_path, 'wb') as f:
                        f.write(compressed_data)

            logger.info(f"Data exported successfully to {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            raise

    async def export_streaming(
        self,
        data_generator: AsyncGenerator[Dict[str, Any], None],
        output_path: str,
        format_type: Optional[ExportFormat] = None
    ) -> str:
        """Export large datasets using streaming"""
        export_format = format_type or self.config.format

        if export_format not in self._exporters:
            raise ValueError(f"Unsupported export format: {export_format}")

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                exporter = self._exporters[export_format]
                if hasattr(exporter, 'export_streaming'):
                    await exporter.export_streaming(data_generator, f)
                else:
                    # Fallback to regular export for formats that don't support streaming
                    data_list = []
                    async for item in data_generator:
                        data_list.append(item)
                    await exporter.export_data(data_list, f)

            logger.info(f"Streaming export completed: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Streaming export failed: {str(e)}")
            raise


# Global export manager instance
_export_manager: Optional[DataExportManager] = None


def get_export_manager() -> DataExportManager:
    """Get the global export manager instance"""
    global _export_manager
    if _export_manager is None:
        _export_manager = DataExportManager()
    return _export_manager


def configure_export_manager(config: ExportConfig):
    """Configure the global export manager"""
    global _export_manager
    _export_manager = DataExportManager(config)


class ExportScheduler:
    """Handles scheduled and batch export operations"""

    def __init__(self):
        self._scheduled_exports: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None

    async def schedule_export(
        self,
        export_id: str,
        export_config: ExportConfig,
        schedule_time: datetime,
        query_params: Dict[str, Any]
    ) -> str:
        """Schedule an export for future execution"""
        async with self._lock:
            self._scheduled_exports[export_id] = {
                "config": export_config,
                "schedule_time": schedule_time,
                "query_params": query_params,
                "status": "scheduled",
                "created_at": datetime.now()
            }

        logger.info(f"Export {export_id} scheduled for {schedule_time}")
        return export_id

    async def start_scheduler(self):
        """Start the export scheduler"""
        if self._running:
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Export scheduler started")

    async def stop_scheduler(self):
        """Stop the export scheduler"""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
        logger.info("Export scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self._running:
            try:
                await self._process_scheduled_exports()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
                await asyncio.sleep(60)

    async def _process_scheduled_exports(self):
        """Process due scheduled exports"""
        now = datetime.now()
        due_exports = []

        async with self._lock:
            for export_id, export_info in self._scheduled_exports.items():
                if (export_info["status"] == "scheduled" and
                    export_info["schedule_time"] <= now):
                    due_exports.append((export_id, export_info))

        for export_id, export_info in due_exports:
            try:
                await self._execute_scheduled_export(export_id, export_info)
            except Exception as e:
                logger.error(f"Failed to execute scheduled export {export_id}: {str(e)}")
                async with self._lock:
                    if export_id in self._scheduled_exports:
                        self._scheduled_exports[export_id]["status"] = "failed"
                        self._scheduled_exports[export_id]["error"] = str(e)

    async def _execute_scheduled_export(self, export_id: str, export_info: Dict[str, Any]):
        """Execute a scheduled export"""
        async with self._lock:
            if export_id in self._scheduled_exports:
                self._scheduled_exports[export_id]["status"] = "running"

        try:
            # This would need to be integrated with the actual data source
            # For now, it's a placeholder
            export_manager = get_export_manager()

            # Create output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"exports/scheduled_{export_id}_{timestamp}.json"

            # Execute export (placeholder - would need actual data)
            # await export_manager.export_data(data, output_path)

            async with self._lock:
                if export_id in self._scheduled_exports:
                    self._scheduled_exports[export_id]["status"] = "completed"
                    self._scheduled_exports[export_id]["output_path"] = output_path
                    self._scheduled_exports[export_id]["completed_at"] = datetime.now()

            logger.info(f"Scheduled export {export_id} completed successfully")

        except Exception as e:
            async with self._lock:
                if export_id in self._scheduled_exports:
                    self._scheduled_exports[export_id]["status"] = "failed"
                    self._scheduled_exports[export_id]["error"] = str(e)
            raise

    async def get_scheduled_exports(self) -> Dict[str, Dict[str, Any]]:
        """Get all scheduled exports"""
        async with self._lock:
            return self._scheduled_exports.copy()

    async def cancel_scheduled_export(self, export_id: str) -> bool:
        """Cancel a scheduled export"""
        async with self._lock:
            if export_id in self._scheduled_exports:
                if self._scheduled_exports[export_id]["status"] == "scheduled":
                    self._scheduled_exports[export_id]["status"] = "cancelled"
                    logger.info(f"Cancelled scheduled export {export_id}")
                    return True
        return False


# Global scheduler instance
_export_scheduler: Optional[ExportScheduler] = None


def get_export_scheduler() -> ExportScheduler:
    """Get the global export scheduler instance"""
    global _export_scheduler
    if _export_scheduler is None:
        _export_scheduler = ExportScheduler()
    return _export_scheduler
