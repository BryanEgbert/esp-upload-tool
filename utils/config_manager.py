import json
import os
from typing import Dict, Optional

class ConfigManager:
    CONFIG_FILE = "provisioning_config.json"

    @staticmethod
    def load_config() -> Dict:
        if not os.path.exists(ConfigManager.CONFIG_FILE):
            return {}
        try:
            with open(ConfigManager.CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def save_config(config: Dict):
        try:
            with open(ConfigManager.CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    @staticmethod
    def get_persistent_key_path(chip_type: str, key_type: str) -> Optional[str]:
        """
        key_type can be 'flash_encryption' or 'secure_boot'
        """
        config = ConfigManager.load_config()
        chip_configs = config.get("persistent_keys", {})
        return chip_configs.get(chip_type, {}).get(key_type)

    @staticmethod
    def set_persistent_key_path(chip_type: str, key_type: str, path: str):
        config = ConfigManager.load_config()
        if "persistent_keys" not in config:
            config["persistent_keys"] = {}
        if chip_type not in config["persistent_keys"]:
            config["persistent_keys"][chip_type] = {}
        
        config["persistent_keys"][chip_type][key_type] = path
        ConfigManager.save_config(config)

    @staticmethod
    def get_last_config() -> Dict:
        config = ConfigManager.load_config()
        return config.get("last_config", {})

    @staticmethod
    def save_last_config(last_config: Dict):
        config = ConfigManager.load_config()
        config["last_config"] = last_config
        ConfigManager.save_config(config)
