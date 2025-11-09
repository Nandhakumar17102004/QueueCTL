import json
import os
from pathlib import Path
from typing import Any, Dict


class ConfigManager:    
    DEFAULT_CONFIG = {
        "max_retries": 3,
        "retry_backoff_base": 2,
        "job_timeout": 300,
        "worker_poll_interval": 1,
        "max_concurrent_jobs": 4,
        "db_path": "data/queuectl.db",
        "log_path": "logs/queuectl.log",
        "config_path": "config/queuectl.json"
    }
    
    VALIDATORS = {
        "max_retries": lambda x: isinstance(x, int) and x >= 0,
        "retry_backoff_base": lambda x: isinstance(x, (int, float)) and x >= 1,
        "job_timeout": lambda x: isinstance(x, int) and x > 0,
        "worker_poll_interval": lambda x: isinstance(x, (int, float)) and x > 0,
        "max_concurrent_jobs": lambda x: isinstance(x, int) and x > 0,
        "db_path": lambda x: isinstance(x, str) and x.strip() != "",
        "log_path": lambda x: isinstance(x, str) and x.strip() != "",
        "config_path": lambda x: isinstance(x, str) and x.strip() != ""
    }
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or self.DEFAULT_CONFIG["config_path"]
        Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load config from file or create default."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    merged_config = {**self.DEFAULT_CONFIG, **config}
                    self._validate_config(merged_config)
                    return merged_config
            except Exception as e:
                print(f"Error loading config: {e}, using defaults")
                return self.DEFAULT_CONFIG.copy()
        else:
            self._save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()
    
    def _save_config(self, config: Dict[str, Any]) -> bool:
        """Save config to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def _validate_config(self, config: Dict[str, Any]):
        """Validate configuration values."""
        for key, value in config.items():
            if key in self.VALIDATORS and not self.VALIDATORS[key](value):
                raise ValueError(f"Invalid config value for {key}: {value}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> bool:
        """Set config value and persist."""
        if key in self.VALIDATORS and not self.VALIDATORS[key](value):
            raise ValueError(f"Invalid value for {key}: {value}")
        
        self.config[key] = value
        return self._save_config(self.config)
    
    def update_multiple(self, updates: Dict[str, Any]) -> bool:
        """Update multiple config values."""
        for key, value in updates.items():
            if key in self.VALIDATORS and not self.VALIDATORS[key](value):
                raise ValueError(f"Invalid value for {key}: {value}")
        
        self.config.update(updates)
        return self._save_config(self.config)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration."""

        return self.config.copy()
