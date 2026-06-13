from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
from platform_config_loader import PlatformConfigLoader


class BasePlatformHandler(ABC):

    def __init__(self, platform_key: str, config_loader: PlatformConfigLoader):
        self.platform_key = platform_key
        self.config = config_loader.get_platform(platform_key)

        if not self.config:
            raise ValueError(f"Platform '{platform_key}' not found in config")

        if not self.config.enabled:
            raise ValueError(f"Platform '{platform_key}' is disabled")

    @abstractmethod
    def extract_profile_data(self, profile_url: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        pass

    @abstractmethod
    def extract_jobs(self, keyword: str, location: str, max_jobs: int = 20) -> List[Dict]:
        pass

    def get_config(self):
        return self.config


class LinkedInHandler(BasePlatformHandler):

    def validate_url(self, url: str) -> bool:
        return "linkedin.com/in/" in url.lower()

    def extract_profile_data(self, profile_url: str) -> Dict[str, Any]:
        if not self.validate_url(profile_url):
            raise ValueError(f"Invalid LinkedIn URL: {profile_url}")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(profile_url, headers=headers, timeout=self.config.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            return {
                'platform': 'linkedin',
                'url': profile_url,
                'data': {
                    'name': self._extract_text(soup, self.config.selectors.get('profile_name')),
                    'headline': self._extract_text(soup, self.config.selectors.get('headline')),
                    'about': self._extract_text(soup, self.config.selectors.get('about')),
                }
            }
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch LinkedIn profile: {str(e)}")

    def extract_jobs(self, keyword: str, location: str, max_jobs: int = 20) -> List[Dict]:
        from linkedin_scraper import LinkedInJobScraper
        scraper = LinkedInJobScraper()
        return scraper.search_jobs(keyword, location, max_jobs)

    def _extract_text(self, soup: BeautifulSoup, selector: Optional[str]) -> Optional[str]:
        if not selector:
            return None
        element = soup.select_one(selector)
        return element.get_text(strip=True) if element else None


class NaukriHandler(BasePlatformHandler):

    def validate_url(self, url: str) -> bool:
        return "naukri.com" in url.lower() and ("mnjuser" in url.lower() or "profile" in url.lower())

    def extract_profile_data(self, profile_url: str) -> Dict[str, Any]:
        if not self.validate_url(profile_url):
            raise ValueError(f"Invalid Naukri URL: {profile_url}")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(profile_url, headers=headers, timeout=self.config.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            return {
                'platform': 'naukri',
                'url': profile_url,
                'data': {
                    'name': self._extract_text(soup, self.config.selectors.get('profile_name')),
                    'headline': self._extract_text(soup, self.config.selectors.get('headline')),
                    'about': self._extract_text(soup, self.config.selectors.get('about')),
                    'experience': self._extract_list(soup, self.config.selectors.get('experience')),
                    'skills': self._extract_list(soup, self.config.selectors.get('skills')),
                }
            }
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch Naukri profile: {str(e)}")

    def extract_jobs(self, keyword: str, location: str, max_jobs: int = 20) -> List[Dict]:
        url = f"https://www.naukri.com/{keyword.replace(' ', '-')}-jobs-in-{location.replace(' ', '-')}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=self.config.timeout)
        soup = BeautifulSoup(response.content, 'html.parser')
        jobs = []
        cards = soup.select("article.jobTuple")[:max_jobs]
        for card in cards:
            title_el = card.select_one("a.title")
            company_el = card.select_one("a.subTitle")
            location_el = card.select_one("li.location")
            if not title_el:
                continue
            jobs.append({
                "title": title_el.get_text(strip=True),
                "company": company_el.get_text(strip=True) if company_el else "",
                "location": location_el.get_text(strip=True) if location_el else "",
                "url": title_el.get("href", ""),
                "description": "",
                "posted": "",
            })
        return jobs

    def _extract_text(self, soup: BeautifulSoup, selector: Optional[str]) -> Optional[str]:
        if not selector:
            return None
        element = soup.select_one(selector)
        return element.get_text(strip=True) if element else None

    def _extract_list(self, soup: BeautifulSoup, selector: Optional[str]) -> list:
        if not selector:
            return []
        elements = soup.select(selector)
        return [elem.get_text(strip=True) for elem in elements]


class PlatformHandlerFactory:

    HANDLERS = {
        'linkedin': LinkedInHandler,
        'naukri': NaukriHandler,
    }

    @staticmethod
    def get_handler(platform_key: str, config_loader: PlatformConfigLoader):
        handler_class = PlatformHandlerFactory.HANDLERS.get(platform_key.lower())
        if not handler_class:
            raise ValueError(f"No handler found for platform: {platform_key}")
        return handler_class(platform_key, config_loader)

    @staticmethod
    def register_handler(platform_key: str, handler_class):
        PlatformHandlerFactory.HANDLERS[platform_key.lower()] = handler_class
