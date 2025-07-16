"""
Tests for salt persistence functionality

Ensures that encryption salts are properly persisted across application
restarts to prevent data loss.
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from app.core.salt_manager import (
    SaltManager, 
    get_persistent_salt, 
    migrate_existing_salt,
    check_salt_compatibility,
    validate_salt_format
)
from app.core.config import Settings
from app.security.encryption import DataEncryption


class TestSaltManager:
    """Test salt manager functionality"""
    
    def test_salt_generation_and_validation(self):
        """Test salt generation and validation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "test.salt"
            manager = SaltManager(str(salt_file))
            
            # Test salt generation
            salt = manager.generate_salt()
            assert len(salt) == 64
            assert manager.validate_salt(salt)
            
            # Test invalid salts
            assert not manager.validate_salt("")
            assert not manager.validate_salt("invalid")
            assert not manager.validate_salt("12345")  # Too short
            assert not manager.validate_salt("invalid_hex_string_not_hex")
    
    def test_salt_persistence(self):
        """Test that salt is persisted across manager instances"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "persist.salt"
            
            # First manager instance
            manager1 = SaltManager(str(salt_file))
            salt1 = manager1.get_or_create_salt()
            
            # Second manager instance (simulating restart)
            manager2 = SaltManager(str(salt_file))
            salt2 = manager2.get_or_create_salt()
            
            # Should be the same salt
            assert salt1 == salt2
            assert len(salt1) == 64
    
    def test_salt_file_permissions(self):
        """Test that salt file has correct permissions"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "perms.salt"
            manager = SaltManager(str(salt_file))
            
            salt = manager.generate_salt()
            manager.save_salt(salt)
            
            # Check file permissions (should be 0o600 - owner read/write only)
            file_mode = oct(salt_file.stat().st_mode)[-3:]
            assert file_mode == "600"
    
    def test_salt_backup_and_restore(self):
        """Test salt backup and restore functionality"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "original.salt"
            backup_file = Path(temp_dir) / "backup.salt"
            
            manager = SaltManager(str(salt_file))
            original_salt = manager.get_or_create_salt()
            
            # Create backup
            assert manager.backup_salt(str(backup_file))
            assert backup_file.exists()
            
            # Modify original
            new_salt = manager.generate_salt()
            manager.save_salt(new_salt)
            
            # Restore from backup
            assert manager.restore_salt(str(backup_file))
            
            # Verify restoration
            restored_salt = manager.load_salt()
            assert restored_salt == original_salt


class TestSaltMigration:
    """Test salt migration functionality"""
    
    def test_migrate_from_environment(self):
        """Test migrating salt from environment variable"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "migrated.salt"
            test_salt = "1234567890abcdef" * 4  # Valid 64-char hex
            
            # Set environment variable
            with patch.dict(os.environ, {'ENCRYPTION_SALT': test_salt}):
                # Ensure no salt file exists
                assert not salt_file.exists()
                
                # Run migration
                with patch('app.core.salt_manager._salt_manager', SaltManager(str(salt_file))):
                    success = migrate_existing_salt()
                    assert success
                    
                    # Verify salt was saved
                    assert salt_file.exists()
                    
                    # Verify correct salt was saved
                    manager = SaltManager(str(salt_file))
                    loaded_salt = manager.load_salt()
                    assert loaded_salt == test_salt
    
    def test_migration_with_existing_file(self):
        """Test migration when salt file already exists"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "existing.salt"
            existing_salt = "abcdef1234567890" * 4
            
            # Create existing salt file
            manager = SaltManager(str(salt_file))
            manager.save_salt(existing_salt)
            
            # Run migration (should not overwrite)
            with patch('app.core.salt_manager._salt_manager', manager):
                success = migrate_existing_salt("different_salt")
                assert success  # Should succeed but not change anything
                
                # Verify original salt is preserved
                loaded_salt = manager.load_salt()
                assert loaded_salt == existing_salt


class TestSettingsPersistence:
    """Test Settings class salt persistence"""
    
    def test_settings_salt_consistency(self):
        """Test that Settings instances use consistent salt"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "settings.salt"
            
            # Mock the salt manager to use our temp file
            with patch('app.core.salt_manager._salt_manager', SaltManager(str(salt_file))):
                # Clear environment to force auto-generation
                with patch.dict(os.environ, {}, clear=True):
                    # First Settings instance
                    settings1 = Settings()
                    salt1 = settings1.encryption_salt
                    
                    # Second Settings instance
                    settings2 = Settings()
                    salt2 = settings2.encryption_salt
                    
                    # Should be the same
                    assert salt1 == salt2
                    assert len(salt1) == 64


class TestEncryptionConsistency:
    """Test encryption consistency across restarts"""
    
    def test_encryption_survives_restart(self):
        """Test that encrypted data can be decrypted after simulated restart"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "encryption.salt"
            test_data = "sensitive_test_data_123"
            
            # First 'application session'
            manager1 = SaltManager(str(salt_file))
            salt1 = manager1.get_or_create_salt()
            
            # Create mock settings
            class MockSettings:
                encryption_key = "test-key"
                encryption_salt = salt1
            
            # Encrypt data
            with patch('app.security.encryption.settings', MockSettings()):
                encryption1 = DataEncryption()
                encrypted_data = encryption1.encrypt(test_data)
                assert encrypted_data is not None
            
            # Second 'application session' (simulated restart)
            manager2 = SaltManager(str(salt_file))
            salt2 = manager2.get_or_create_salt()
            
            # Verify same salt
            assert salt1 == salt2
            
            # Create new mock settings with same salt
            MockSettings.encryption_salt = salt2
            
            # Decrypt data with new encryption instance
            with patch('app.security.encryption.settings', MockSettings()):
                encryption2 = DataEncryption()
                decrypted_data = encryption2.decrypt(encrypted_data)
                assert decrypted_data == test_data


class TestSaltCompatibility:
    """Test salt compatibility checking"""
    
    def test_compatibility_check(self):
        """Test salt compatibility status checking"""
        with tempfile.TemporaryDirectory() as temp_dir:
            salt_file = Path(temp_dir) / "compat.salt"
            
            # Test with no salt file
            with patch('app.core.salt_manager._salt_manager', SaltManager(str(salt_file))):
                status = check_salt_compatibility()
                assert status["status"] in ["will_generate", "migration_needed"]
                assert not status["salt_file_exists"]
            
            # Test with existing salt file
            manager = SaltManager(str(salt_file))
            test_salt = manager.generate_salt()
            manager.save_salt(test_salt)
            
            with patch('app.core.salt_manager._salt_manager', manager):
                status = check_salt_compatibility()
                assert status["status"] == "good"
                assert status["salt_file_exists"]
                assert status["salt_valid"]


class TestSaltValidation:
    """Test salt format validation"""
    
    def test_validate_salt_format(self):
        """Test salt format validation function"""
        # Valid salts
        assert validate_salt_format("1234567890abcdef" * 4)
        assert validate_salt_format("ABCDEF1234567890" * 4)
        
        # Invalid salts
        assert not validate_salt_format("")
        assert not validate_salt_format("invalid")
        assert not validate_salt_format("12345")  # Too short
        assert not validate_salt_format("invalid_hex_string")
        assert not validate_salt_format("1234567890abcdef" * 3)  # Too short (48 chars)
        assert not validate_salt_format("1234567890abcdef" * 5)  # Too long (80 chars)
