"""
Salt Persistence Manager

Handles persistent storage and retrieval of encryption salts to prevent data loss
on application restarts. Ensures the same salt is used consistently across
application lifecycle.
"""

import logging
import os
import secrets
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SaltManager:
    """Manages persistent storage of encryption salts"""

    def __init__(self, salt_file_path: Optional[str] = None):
        """
        Initialize salt manager
        
        Args:
            salt_file_path: Custom path for salt file. If None, uses default location.
        """
        if salt_file_path:
            self.salt_file = Path(salt_file_path)
        else:
            # Default to .salt file in the application root
            app_root = Path(__file__).parent.parent.parent
            self.salt_file = app_root / ".salt"

        # Ensure the directory exists
        self.salt_file.parent.mkdir(parents=True, exist_ok=True)

    def get_or_create_salt(self) -> str:
        """
        Get existing salt from storage or create a new one if none exists
        
        Returns:
            64-character hexadecimal salt string
        """
        try:
            # Try to load existing salt
            existing_salt = self.load_salt()
            if existing_salt:
                logger.info("Loaded existing encryption salt from persistent storage")
                return existing_salt

            # Generate new salt if none exists
            new_salt = self.generate_salt()
            self.save_salt(new_salt)
            logger.info(f"Generated new encryption salt and saved to {self.salt_file}")
            logger.warning("IMPORTANT: Backup the salt file to prevent data loss!")

            return new_salt

        except Exception as e:
            logger.error(f"Failed to manage salt persistence: {e}")
            # Fallback to generating a temporary salt (not recommended for production)
            logger.warning("Using temporary salt - data may not persist across restarts!")
            return self.generate_salt()

    def load_salt(self) -> Optional[str]:
        """
        Load salt from persistent storage
        
        Returns:
            Salt string if found, None otherwise
        """
        try:
            if not self.salt_file.exists():
                return None

            with open(self.salt_file, 'r', encoding='utf-8') as f:
                salt = f.read().strip()

            # Validate the loaded salt
            if self.validate_salt(salt):
                return salt
            else:
                logger.warning(f"Invalid salt found in {self.salt_file}, will regenerate")
                return None

        except Exception as e:
            logger.error(f"Failed to load salt from {self.salt_file}: {e}")
            return None

    def save_salt(self, salt: str) -> bool:
        """
        Save salt to persistent storage
        
        Args:
            salt: Salt string to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate salt before saving
            if not self.validate_salt(salt):
                logger.error("Cannot save invalid salt")
                return False

            # Write salt to file with restricted permissions
            with open(self.salt_file, 'w', encoding='utf-8') as f:
                f.write(salt)

            # Set restrictive file permissions (owner read/write only)
            os.chmod(self.salt_file, 0o600)

            logger.info(f"Salt saved to {self.salt_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save salt to {self.salt_file}: {e}")
            return False

    def generate_salt(self) -> str:
        """
        Generate a new 64-character hexadecimal salt
        
        Returns:
            64-character hex salt string
        """
        return secrets.token_hex(32)  # 32 bytes = 64 hex characters

    def validate_salt(self, salt: str) -> bool:
        """
        Validate that a salt is properly formatted
        
        Args:
            salt: Salt string to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not salt or not isinstance(salt, str):
            return False

        # Check length (should be 64 characters for 32-byte salt)
        if len(salt) != 64:
            return False

        # Check if it's valid hexadecimal
        try:
            bytes.fromhex(salt)
            return True
        except ValueError:
            return False

    def backup_salt(self, backup_path: str) -> bool:
        """
        Create a backup of the current salt
        
        Args:
            backup_path: Path where to save the backup
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.salt_file.exists():
                logger.warning("No salt file exists to backup")
                return False

            backup_file = Path(backup_path)
            backup_file.parent.mkdir(parents=True, exist_ok=True)

            # Copy salt file to backup location
            with open(self.salt_file, 'r', encoding='utf-8') as src:
                salt = src.read()

            with open(backup_file, 'w', encoding='utf-8') as dst:
                dst.write(salt)

            # Set restrictive permissions on backup
            os.chmod(backup_file, 0o600)

            logger.info(f"Salt backed up to {backup_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to backup salt: {e}")
            return False

    def restore_salt(self, backup_path: str) -> bool:
        """
        Restore salt from a backup
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            backup_file = Path(backup_path)
            if not backup_file.exists():
                logger.error(f"Backup file not found: {backup_file}")
                return False

            with open(backup_file, 'r', encoding='utf-8') as f:
                salt = f.read().strip()

            if not self.validate_salt(salt):
                logger.error("Backup contains invalid salt")
                return False

            return self.save_salt(salt)

        except Exception as e:
            logger.error(f"Failed to restore salt from backup: {e}")
            return False


# Global salt manager instance
_salt_manager = None


def get_salt_manager() -> SaltManager:
    """Get the global salt manager instance"""
    global _salt_manager
    if _salt_manager is None:
        _salt_manager = SaltManager()
    return _salt_manager


def get_persistent_salt() -> str:
    """
    Get or create a persistent encryption salt
    
    Returns:
        64-character hexadecimal salt string
    """
    return get_salt_manager().get_or_create_salt()


def validate_salt_format(salt: str) -> bool:
    """
    Validate salt format

    Args:
        salt: Salt string to validate

    Returns:
        True if valid, False otherwise
    """
    return get_salt_manager().validate_salt(salt)


def migrate_existing_salt(old_salt: Optional[str] = None) -> bool:
    """
    Migrate existing salt to persistent storage

    This function helps existing installations migrate to the new persistent
    salt system without losing access to previously encrypted data.

    Args:
        old_salt: Existing salt to migrate. If None, will check environment variables.

    Returns:
        True if migration successful, False otherwise
    """
    try:
        salt_manager = get_salt_manager()

        # Check if salt file already exists
        if salt_manager.salt_file.exists():
            logger.info("Salt file already exists, no migration needed")
            return True

        # Try to get salt from parameter or environment
        migration_salt = old_salt
        if not migration_salt:
            # Check common environment variable names
            migration_salt = os.environ.get('ENCRYPTION_SALT')

        if not migration_salt:
            # Check for legacy environment variables
            migration_salt = os.environ.get('LEGACY_ENCRYPTION_SALT')

        if migration_salt and salt_manager.validate_salt(migration_salt):
            # Save the existing salt to persistent storage
            if salt_manager.save_salt(migration_salt):
                logger.info("Successfully migrated existing salt to persistent storage")
                logger.info(f"Salt saved to: {salt_manager.salt_file}")
                return True
            else:
                logger.error("Failed to save migrated salt")
                return False
        else:
            logger.info("No existing salt found to migrate, will generate new one")
            return True

    except Exception as e:
        logger.error(f"Salt migration failed: {e}")
        return False


def check_salt_compatibility() -> dict:
    """
    Check salt configuration compatibility and provide status information

    Returns:
        Dictionary with compatibility status and recommendations
    """
    try:
        salt_manager = get_salt_manager()
        status = {
            "salt_file_exists": salt_manager.salt_file.exists(),
            "salt_file_path": str(salt_manager.salt_file),
            "env_salt_configured": bool(os.environ.get('ENCRYPTION_SALT')),
            "recommendations": [],
            "warnings": [],
            "status": "unknown"
        }

        # Check if salt file exists
        if status["salt_file_exists"]:
            # Validate the salt file
            stored_salt = salt_manager.load_salt()
            if stored_salt:
                status["salt_valid"] = True
                status["salt_length"] = len(stored_salt)
                status["status"] = "good"
            else:
                status["salt_valid"] = False
                status["warnings"].append("Salt file exists but contains invalid salt")
                status["recommendations"].append("Remove invalid salt file and restart application")
                status["status"] = "warning"
        else:
            status["salt_valid"] = False

            # Check if environment variable is set
            if status["env_salt_configured"]:
                env_salt = os.environ.get('ENCRYPTION_SALT')
                if salt_manager.validate_salt(env_salt):
                    status["recommendations"].append("Run migration to move environment salt to persistent storage")
                    status["status"] = "migration_needed"
                else:
                    status["warnings"].append("Environment ENCRYPTION_SALT is invalid")
                    status["recommendations"].append("Fix ENCRYPTION_SALT format or remove to auto-generate")
                    status["status"] = "error"
            else:
                status["recommendations"].append("Salt will be auto-generated on first use")
                status["status"] = "will_generate"

        return status

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "recommendations": ["Check application logs for detailed error information"]
        }
