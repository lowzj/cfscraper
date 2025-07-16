"""
Data Encryption and Privacy

Provides encryption utilities for sensitive data storage and transmission.
"""

import base64
import hashlib
import secrets
from typing import Optional, Union, Any
import logging
import json

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings

logger = logging.getLogger(__name__)


class DataEncryption:
    """Data encryption utilities using Fernet (AES 128)"""
    
    def __init__(self, encryption_key: Optional[str] = None):
        self.encryption_key = encryption_key or settings.encryption_key
        self._fernet = None
        self._initialize_fernet()
    
    def _initialize_fernet(self):
        """Initialize Fernet cipher with derived key"""
        try:
            # Derive a proper key from the encryption key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'cfscraper_salt',  # In production, use a random salt per installation
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(self.encryption_key.encode()))
            self._fernet = Fernet(key)
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            self._fernet = None
    
    def encrypt(self, data: Union[str, dict, list]) -> Optional[str]:
        """Encrypt data and return base64 encoded string"""
        if not self._fernet:
            logger.warning("Encryption not available, returning data as-is")
            return str(data) if not isinstance(data, str) else data
        
        try:
            # Convert data to JSON string if not already a string
            if isinstance(data, (dict, list)):
                data_str = json.dumps(data)
            else:
                data_str = str(data)
            
            # Encrypt and encode
            encrypted_data = self._fernet.encrypt(data_str.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return None
    
    def decrypt(self, encrypted_data: str) -> Optional[str]:
        """Decrypt base64 encoded encrypted data"""
        if not self._fernet:
            logger.warning("Encryption not available, returning data as-is")
            return encrypted_data
        
        try:
            # Decode and decrypt
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self._fernet.decrypt(encrypted_bytes)
            return decrypted_data.decode()
        
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None
    
    def decrypt_json(self, encrypted_data: str) -> Optional[Union[dict, list]]:
        """Decrypt and parse JSON data"""
        decrypted_str = self.decrypt(encrypted_data)
        if decrypted_str:
            try:
                return json.loads(decrypted_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse decrypted JSON: {e}")
        return None
    
    def hash_data(self, data: str, salt: Optional[str] = None) -> str:
        """Create a secure hash of data"""
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Combine data and salt
        combined = f"{data}{salt}".encode()
        
        # Create hash
        hash_obj = hashlib.sha256(combined)
        return f"{salt}:{hash_obj.hexdigest()}"
    
    def verify_hash(self, data: str, hashed_data: str) -> bool:
        """Verify data against hash"""
        try:
            salt, hash_value = hashed_data.split(':', 1)
            expected_hash = self.hash_data(data, salt)
            return expected_hash == hashed_data
        except Exception as e:
            logger.error(f"Hash verification failed: {e}")
            return False


# Global encryption instance
_encryption_instance = None


def get_encryption_instance() -> DataEncryption:
    """Get global encryption instance"""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = DataEncryption()
    return _encryption_instance


def encrypt_sensitive_data(data: Any) -> Optional[str]:
    """Encrypt sensitive data"""
    encryption = get_encryption_instance()
    return encryption.encrypt(data)


def decrypt_sensitive_data(encrypted_data: str) -> Optional[str]:
    """Decrypt sensitive data"""
    encryption = get_encryption_instance()
    return encryption.decrypt(encrypted_data)


def hash_sensitive_data(data: str) -> str:
    """Hash sensitive data"""
    encryption = get_encryption_instance()
    return encryption.hash_data(data)


def verify_sensitive_data(data: str, hashed_data: str) -> bool:
    """Verify sensitive data against hash"""
    encryption = get_encryption_instance()
    return encryption.verify_hash(data, hashed_data)


class EncryptedField:
    """Database field that automatically encrypts/decrypts data"""
    
    def __init__(self, encryption: DataEncryption = None):
        self.encryption = encryption or get_encryption_instance()
    
    def encrypt_for_storage(self, value: Any) -> Optional[str]:
        """Encrypt value for database storage"""
        if value is None:
            return None
        return self.encryption.encrypt(value)
    
    def decrypt_from_storage(self, encrypted_value: str) -> Optional[str]:
        """Decrypt value from database storage"""
        if not encrypted_value:
            return None
        return self.encryption.decrypt(encrypted_value)


class DataAnonymizer:
    """Anonymize sensitive data for logs and analytics"""
    
    @staticmethod
    def anonymize_ip(ip: str) -> str:
        """Anonymize IP address"""
        if not ip or ip == "unknown":
            return ip
        
        parts = ip.split('.')
        if len(parts) == 4:  # IPv4
            return f"{parts[0]}.{parts[1]}.xxx.xxx"
        
        # IPv6 - keep first 4 groups
        if ':' in ip:
            parts = ip.split(':')
            if len(parts) >= 4:
                return ':'.join(parts[:4]) + '::xxxx'
        
        return "xxx.xxx.xxx.xxx"
    
    @staticmethod
    def anonymize_email(email: str) -> str:
        """Anonymize email address"""
        if not email or '@' not in email:
            return email
        
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            return f"x@{domain}"
        
        return f"{local[0]}{'x' * (len(local) - 2)}{local[-1]}@{domain}"
    
    @staticmethod
    def anonymize_url(url: str) -> str:
        """Anonymize URL by removing query parameters and sensitive paths"""
        if not url:
            return url
        
        # Remove query parameters
        if '?' in url:
            url = url.split('?')[0]
        
        # Replace sensitive path segments
        sensitive_patterns = [
            '/api/key/',
            '/admin/',
            '/user/',
            '/auth/'
        ]
        
        for pattern in sensitive_patterns:
            if pattern in url:
                url = url.replace(pattern, '/***/')
        
        return url
    
    @staticmethod
    def anonymize_user_agent(user_agent: str) -> str:
        """Anonymize user agent string"""
        if not user_agent:
            return user_agent
        
        # Keep browser and OS info, remove detailed version numbers
        import re
        
        # Remove detailed version numbers
        user_agent = re.sub(r'\d+\.\d+\.\d+\.\d+', 'x.x.x.x', user_agent)
        user_agent = re.sub(r'\d+\.\d+\.\d+', 'x.x.x', user_agent)
        
        return user_agent


def anonymize_log_data(data: dict) -> dict:
    """Anonymize sensitive data in log entries"""
    anonymizer = DataAnonymizer()
    anonymized = data.copy()
    
    # Anonymize common sensitive fields
    if 'ip' in anonymized:
        anonymized['ip'] = anonymizer.anonymize_ip(anonymized['ip'])
    
    if 'email' in anonymized:
        anonymized['email'] = anonymizer.anonymize_email(anonymized['email'])
    
    if 'url' in anonymized:
        anonymized['url'] = anonymizer.anonymize_url(anonymized['url'])
    
    if 'user_agent' in anonymized:
        anonymized['user_agent'] = anonymizer.anonymize_user_agent(anonymized['user_agent'])
    
    # Remove sensitive headers
    if 'headers' in anonymized and isinstance(anonymized['headers'], dict):
        sensitive_headers = ['authorization', 'x-api-key', 'cookie', 'x-auth-token']
        for header in sensitive_headers:
            if header in anonymized['headers']:
                anonymized['headers'][header] = '***'
    
    return anonymized


def generate_encryption_key() -> str:
    """Generate a new encryption key"""
    return Fernet.generate_key().decode()


def rotate_encryption_key(old_key: str, new_key: str, encrypted_data: str) -> Optional[str]:
    """Rotate encryption key by re-encrypting data"""
    try:
        # Decrypt with old key
        old_encryption = DataEncryption(old_key)
        decrypted_data = old_encryption.decrypt(encrypted_data)
        
        if decrypted_data is None:
            return None
        
        # Encrypt with new key
        new_encryption = DataEncryption(new_key)
        return new_encryption.encrypt(decrypted_data)
    
    except Exception as e:
        logger.error(f"Key rotation failed: {e}")
        return None
