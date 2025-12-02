import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import shutil

logger = logging.getLogger(__name__)


class BucketManager:
    """
    Manages data bucketing for hourly summaries and daily analysis.
    
    Structure:
    - bucket/raw/{timestamp}.json - Raw metrics for 1 hour (deleted after 1 hour)
    - bucket/processed/{date}/{hour}.json - Processed hourly summaries (kept for 24 hours)
    """
    
    def __init__(self, base_path: str = None):
        """Initialize bucket manager with base directory"""
        if base_path is None:
            # Default to analysis/bucket directory
            base_path = os.path.join(os.path.dirname(__file__), "..", "..", "bucket")
        
        self.base_path = Path(base_path)
        self.raw_path = self.base_path / "raw"
        self.processed_path = self.base_path / "processed"
        
        # Create directories if they don't exist
        self.raw_path.mkdir(parents=True, exist_ok=True)
        self.processed_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"BucketManager initialized at {self.base_path}")
    
    def save_hourly_raw(self, data: Dict[str, Any], timestamp: datetime) -> str:
        """
        Save raw hourly metrics data to bucket.
        
        Args:
            data: Raw metrics data dictionary
            timestamp: Timestamp for this data
            
        Returns:
            Path to saved file
        """
        try:
            # Format filename as ISO timestamp
            filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            filepath = self.raw_path / filename
            
            # Add metadata
            bucket_data = {
                "timestamp": timestamp.isoformat(),
                "created_at": datetime.now().isoformat(),
                "type": "raw",
                "data": data
            }
            
            # Write to file
            with open(filepath, 'w') as f:
                json.dump(bucket_data, f, indent=2)
            
            logger.info(f"Saved raw hourly data to {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to save raw hourly data: {e}", exc_info=True)
            raise
    
    def get_hourly_raw(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        """
        Retrieve raw data from buckets within time range.
        
        Args:
            start: Start timestamp
            end: End timestamp
            
        Returns:
            List of raw data dictionaries
        """
        try:
            results = []
            
            # List all files in raw directory
            if not self.raw_path.exists():
                return results
            
            for filepath in self.raw_path.glob("*.json"):
                try:
                    with open(filepath, 'r') as f:
                        bucket_data = json.load(f)
                    
                    # Parse timestamp
                    file_timestamp = datetime.fromisoformat(bucket_data["timestamp"])
                    
                    # Check if within range
                    if start <= file_timestamp <= end:
                        results.append(bucket_data)
                        
                except Exception as e:
                    logger.warning(f"Failed to read bucket file {filepath}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(results)} raw bucket files from {start} to {end}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to retrieve raw hourly data: {e}", exc_info=True)
            return []
    
    def save_hourly_processed(self, summary: Dict[str, Any], timestamp: datetime, hostname: str = None) -> str:
        """
        Save processed hourly summary to bucket.
        
        Args:
            summary: Processed hourly summary data
            timestamp: Timestamp for this summary
            hostname: Optional hostname for server-specific summaries
            
        Returns:
            Path to saved file
        """
        try:
            # Create date-based subdirectory
            date_str = timestamp.strftime('%Y%m%d')
            date_dir = self.processed_path / date_str
            date_dir.mkdir(exist_ok=True)
            
            # Format filename
            hour_str = timestamp.strftime('%H')
            if hostname:
                filename = f"{hour_str}_{hostname}.json"
            else:
                filename = f"{hour_str}_all.json"
            
            filepath = date_dir / filename
            
            # Add metadata
            bucket_data = {
                "timestamp": timestamp.isoformat(),
                "hostname": hostname,
                "created_at": datetime.now().isoformat(),
                "type": "processed",
                "summary": summary
            }
            
            # Write to file
            with open(filepath, 'w') as f:
                json.dump(bucket_data, f, indent=2)
            
            logger.info(f"Saved processed hourly summary to {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to save processed hourly summary: {e}", exc_info=True)
            raise
    
    def get_daily_processed(self, date: datetime, hostname: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve all processed hourly summaries for a specific date.
        
        Args:
            date: Date to retrieve summaries for
            hostname: Optional hostname filter
            
        Returns:
            List of processed summary dictionaries (up to 24 hours)
        """
        try:
            results = []
            
            # Get date directory
            date_str = date.strftime('%Y%m%d')
            date_dir = self.processed_path / date_str
            
            if not date_dir.exists():
                logger.warning(f"No processed data found for date {date_str}")
                return results
            
            # Pattern for files
            if hostname:
                pattern = f"*_{hostname}.json"
            else:
                pattern = "*_all.json"
            
            # Read all matching files
            for filepath in sorted(date_dir.glob(pattern)):
                try:
                    with open(filepath, 'r') as f:
                        bucket_data = json.load(f)
                    results.append(bucket_data)
                    
                except Exception as e:
                    logger.warning(f"Failed to read bucket file {filepath}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(results)} processed summaries for date {date_str}{f' (hostname={hostname})' if hostname else ''}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to retrieve daily processed data: {e}", exc_info=True)
            return []
    
    def cleanup_old_buckets(self) -> Dict[str, int]:
        """
        Clean up old bucket files based on retention policy:
        - Raw data: Keep only last 1 hour
        - Processed data: Keep last 24 hours
        
        Returns:
            Dictionary with cleanup stats
        """
        try:
            now = datetime.now()
            stats = {
                "raw_deleted": 0,
                "processed_deleted": 0,
                "errors": 0
            }
            
            # Clean raw data (older than 1 hour)
            raw_cutoff = now - timedelta(hours=1)
            if self.raw_path.exists():
                for filepath in self.raw_path.glob("*.json"):
                    try:
                        with open(filepath, 'r') as f:
                            bucket_data = json.load(f)
                        
                        file_timestamp = datetime.fromisoformat(bucket_data["timestamp"])
                        
                        if file_timestamp < raw_cutoff:
                            filepath.unlink()
                            stats["raw_deleted"] += 1
                            logger.debug(f"Deleted old raw bucket: {filepath}")
                            
                    except Exception as e:
                        logger.warning(f"Error cleaning up {filepath}: {e}")
                        stats["errors"] += 1
            
            # Clean processed data (older than 24 hours)
            processed_cutoff_date = (now - timedelta(hours=24)).date()
            if self.processed_path.exists():
                for date_dir in self.processed_path.iterdir():
                    if not date_dir.is_dir():
                        continue
                    
                    try:
                        # Parse directory name as date (YYYYMMDD)
                        dir_date = datetime.strptime(date_dir.name, '%Y%m%d').date()
                        
                        if dir_date < processed_cutoff_date:
                            # Remove entire directory
                            shutil.rmtree(date_dir)
                            # Count files that were deleted
                            file_count = len(list(date_dir.glob("*.json")))
                            stats["processed_deleted"] += file_count
                            logger.info(f"Deleted old processed bucket directory: {date_dir} ({file_count} files)")
                            
                    except Exception as e:
                        logger.warning(f"Error cleaning up directory {date_dir}: {e}")
                        stats["errors"] += 1
            
            logger.info(f"Bucket cleanup complete: deleted {stats['raw_deleted']} raw files, "
                       f"{stats['processed_deleted']} processed files, {stats['errors']} errors")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to cleanup old buckets: {e}", exc_info=True)
            return {"raw_deleted": 0, "processed_deleted": 0, "errors": 1}
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics for bucket system.
        
        Returns:
            Dictionary with storage stats
        """
        try:
            stats = {
                "raw_files": 0,
                "raw_size_mb": 0.0,
                "processed_files": 0,
                "processed_size_mb": 0.0,
                "total_size_mb": 0.0
            }
            
            # Count raw files
            if self.raw_path.exists():
                raw_files = list(self.raw_path.glob("*.json"))
                stats["raw_files"] = len(raw_files)
                stats["raw_size_mb"] = sum(f.stat().st_size for f in raw_files) / (1024 * 1024)
            
            # Count processed files
            if self.processed_path.exists():
                processed_files = list(self.processed_path.rglob("*.json"))
                stats["processed_files"] = len(processed_files)
                stats["processed_size_mb"] = sum(f.stat().st_size for f in processed_files) / (1024 * 1024)
            
            stats["total_size_mb"] = stats["raw_size_mb"] + stats["processed_size_mb"]
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}", exc_info=True)
            return {}
