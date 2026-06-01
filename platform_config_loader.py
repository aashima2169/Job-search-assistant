import json
import os
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class PlatformConfig:
    """Data class for platform configuration"""
    name: str
    base_url: str
    profile_url_pattern: str
    enabled: bool
    scraper_type: str
    timeout: int
    selectors: Dict[str, str]
    api_method: str
    requires_auth: bool
    metadata: Dict


class PlatformConfigLoader:
    """Load and manage platform configurations"""
    
    def __init__(self, config_path: str = "platforms_config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.platforms = self._parse_platforms()
    
    def _load_config(self) -> Dict:
        """Load JSON config file"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def _parse_platforms(self) -> Dict[str, PlatformConfig]:
        """Parse platform configs into PlatformConfig objects"""
        platforms = {}
        for platform_key, platform_data in self.config.get("platforms", {}).items():
            platforms[platform_key] = PlatformConfig(
                name=platform_data["name"],
                base_url=platform_data["base_url"],
                profile_url_pattern=platform_data["profile_url_pattern"],
                enabled=platform_data["enabled"],
                scraper_type=platform_data["scraper_type"],
                timeout=platform_data["timeout"],
                selectors=platform_data["selectors"],
                api_method=platform_data["api_method"],
                requires_auth=platform_data["requires_auth"],
                metadata=platform_data["metadata"]
            )
        return platforms
    
    def get_platform(self, platform_key: str) -> Optional[PlatformConfig]:
        """Get a specific platform config"""
        return self.platforms.get(platform_key)
    
    def get_enabled_platforms(self) -> List[str]:
        """Get list of enabled platform keys"""
        return [key for key, config in self.platforms.items() if config.enabled]
    
    def add_platform(self, platform_key: str, platform_data: Dict) -> None:
        """Add a new platform to config"""
        self.config["platforms"][platform_key] = platform_data
        self._save_config()
        self.platforms = self._parse_platforms()
        print(f"✅ Platform '{platform_key}' added successfully")
    
    def update_platform(self, platform_key: str, updates: Dict) -> None:
        """Update existing platform config"""
        if platform_key not in self.config["platforms"]:
            raise ValueError(f"Platform '{platform_key}' not found")
        
        self.config["platforms"][platform_key].update(updates)
        self._save_config()
        self.platforms = self._parse_platforms()
        print(f"✅ Platform '{platform_key}' updated successfully")
    
    def enable_platform(self, platform_key: str) -> None:
        """Enable a platform"""
        self.update_platform(platform_key, {"enabled": True})
    
    def disable_platform(self, platform_key: str) -> None:
        """Disable a platform"""
        self.update_platform(platform_key, {"enabled": False})
    
    def list_platforms(self) -> None:
        """Print all available platforms"""
        print("\n📋 Available Platforms:\n")
        for key, config in self.platforms.items():
            status = "✅ Enabled" if config.enabled else "❌ Disabled"
            print(f"  {key.upper()}")
            print(f"    Name: {config.name}")
            print(f"    Status: {status}")
            print(f"    Scraper Type: {config.scraper_type}")
            print(f"    Selectors: {list(config.selectors.keys())}")
            print()
    
    def _save_config(self) -> None:
        """Save config back to JSON file"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)


# Example usage
if __name__ == "__main__":
    loader = PlatformConfigLoader()
    
    # List all platforms
    loader.list_platforms()
    
    # Get specific platform
    linkedin_config = loader.get_platform("linkedin")
    print(f"\nLinkedIn Config: {linkedin_config}\n")
    
    # Get enabled platforms
    enabled = loader.get_enabled_platforms()
    print(f"Enabled platforms: {enabled}")
