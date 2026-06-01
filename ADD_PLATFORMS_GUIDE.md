# 📋 Adding New Platforms to Push

## Quick Start: Add a Platform to platforms_config.json

### Step 1: Add Platform Config

Edit `platforms_config.json` and add a new entry:

```json
{
  "platforms": {
    "twitter": {
      "name": "Twitter/X",
      "base_url": "https://twitter.com",
      "profile_url_pattern": "https://twitter.com/{username}",
      "enabled": true,
      "scraper_type": "http",
      "timeout": 10,
      "selectors": {
        "profile_name": "span[data-text='true']",
        "bio": "div[data-testid='UserDescription']",
        "followers": "span[data-testid='FollowersCount']"
      },
      "api_method": "none",
      "requires_auth": false,
      "metadata": {
        "description": "Twitter profile scraping",
        "last_updated": "2025-06-01"
      }
    }
  }
}
```

### Step 2: Create Handler Class

Add to `platform_handlers.py`:

```python
class TwitterHandler(BasePlatformHandler):
    """Handler for Twitter/X profile scraping"""
    
    def validate_url(self, url: str) -> bool:
        """Check if URL is a Twitter profile"""
        return "twitter.com" in url.lower() or "x.com" in url.lower()
    
    def extract_profile_data(self, profile_url: str) -> Dict[str, Any]:
        """Extract Twitter profile data"""
        if not self.validate_url(profile_url):
            raise ValueError(f"Invalid Twitter URL: {profile_url}")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(profile_url, headers=headers, timeout=self.config.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            profile_data = {
                'platform': 'twitter',
                'url': profile_url,
                'data': {
                    'name': self._extract_text(soup, self.config.selectors.get('profile_name')),
                    'bio': self._extract_text(soup, self.config.selectors.get('bio')),
                    'followers': self._extract_text(soup, self.config.selectors.get('followers')),
                }
            }
            
            return profile_data
        
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch Twitter profile: {str(e)}")
    
    def _extract_text(self, soup: BeautifulSoup, selector: Optional[str]) -> Optional[str]:
        if not selector:
            return None
        element = soup.select_one(selector)
        return element.get_text(strip=True) if element else None
```

### Step 3: Register Handler

In `platform_handlers.py`, update the `PlatformHandlerFactory`:

```python
class PlatformHandlerFactory:
    HANDLERS = {
        'linkedin': LinkedInHandler,
        'naukri': NaukriHandler,
        'twitter': TwitterHandler,  # ← Add this
    }
```

### Step 4: Use It

```python
from platform_config_loader import PlatformConfigLoader
from platform_handlers import PlatformHandlerFactory

loader = PlatformConfigLoader()
twitter_handler = PlatformHandlerFactory.get_handler('twitter', loader)

# Extract profile data
profile_data = twitter_handler.extract_profile_data("https://twitter.com/some_user")
print(profile_data)
```

---

## Managing Platforms Programmatically

### Add Platform via Code

```python
from platform_config_loader import PlatformConfigLoader

loader = PlatformConfigLoader()

new_platform = {
    "name": "GitHub",
    "base_url": "https://github.com",
    "profile_url_pattern": "https://github.com/{username}",
    "enabled": True,
    "scraper_type": "http",
    "timeout": 10,
    "selectors": {
        "profile_name": "span[itemprop='name']",
        "bio": "span[data-bio-text]",
        "followers": "span[title='Followers']"
    },
    "api_method": "rest",
    "requires_auth": False,
    "metadata": {
        "description": "GitHub profile",
        "last_updated": "2025-06-01"
    }
}

loader.add_platform("github", new_platform)
```

### List All Platforms

```python
loader.list_platforms()
```

### Enable/Disable Platform

```python
loader.disable_platform("linkedin")
loader.enable_platform("linkedin")
```

### Update Selectors

```python
updates = {
    "selectors": {
        "profile_name": "h1.new-selector",
        "bio": "div.bio-new"
    }
}

loader.update_platform("naukri", updates)
```

---

## Best Practices

1. **Test selectors before adding** - Inspect the website and verify CSS selectors work
2. **Set appropriate timeouts** - Different sites need different times
3. **Handle failures gracefully** - Use try/except in handlers
4. **Update metadata** - Keep `last_updated` current
5. **Document selectors** - Add comments explaining what each selector extracts
6. **Use meaningful names** - Platform keys should be lowercase and simple (linkedin, twitter, etc)

---

## Troubleshooting

**Issue**: Selectors not working
- **Solution**: Websites change HTML structure. Use browser dev tools to find new selectors and update config.

**Issue**: Website blocking requests
- **Solution**: Use Selenium/Playwright instead of requests. Change `scraper_type` to `headless_browser`.

**Issue**: Need authentication
- **Solution**: Set `requires_auth: true` and implement auth logic in handler.

---

## Next Steps

1. ✅ Test LinkedIn and Naukri handlers
2. ✅ Add more platforms as needed
3. ✅ Create FastAPI endpoints that use handlers
4. ✅ Build UI to manage platform configs
