import os
import requests
from typing import List, Dict

class LinkedInJobScraper:
    
    def __init__(self):
        self.api_key = os.getenv("SCRAPINGBEE_API_KEY")
        self.li_at = os.getenv("LI_AT_COOKIE")
        
        if not self.api_key:
            raise ValueError("SCRAPINGBEE_API_KEY not set")
        if not self.li_at:
            raise ValueError("LI_AT_COOKIE not set")
    
    def _scrape_url(self, url: str) -> str:
        """Fetch a URL through ScrapingBee with your LinkedIn cookie"""
        response = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": self.api_key,
                "url": url,
                "render_js": "true",
                "cookies": f"li_at={self.li_at}",
                "wait": 2000,  # wait 2s for JS to render
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"ScrapingBee error {response.status_code}: {response.text}")
        
        return response.text
    
    def search_jobs(self, keyword: str, location: str, max_jobs: int = 20) -> List[Dict]:
        from bs4 import BeautifulSoup
        
        search_url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={keyword.replace(' ', '%20')}"
            f"&location={location.replace(' ', '%20')}"
            f"&f_TPR=r604800"
        )
        
        print(f"Searching: {search_url}")
        html = self._scrape_url(search_url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if cookie worked
        if "authwall" in html or "sign in" in html.lower():
            raise Exception("LinkedIn cookie expired — refresh LI_AT_COOKIE in Vercel env")
        
        job_cards = soup.select("div.job-search-card")
        print(f"Found {len(job_cards)} job cards")
        
        jobs = []
        for card in job_cards[:max_jobs]:
            try:
                title_el = card.select_one("h3.base-search-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle")
                location_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a.base-card__full-link")
                posted_el = card.select_one("time")
                
                if not title_el or not link_el:
                    continue
                
                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True) if company_el else "",
                    "location": location_el.get_text(strip=True) if location_el else "",
                    "url": link_el.get("href", ""),
                    "posted": posted_el.get("datetime", "") if posted_el else "",
                    "description": ""
                })
            except Exception as e:
                print(f"Failed to parse card: {e}")
                continue
        
        # Enrich with full descriptions
        jobs = self._enrich_with_descriptions(jobs)
        return jobs
    
    def _enrich_with_descriptions(self, jobs: List[Dict]) -> List[Dict]:
        from bs4 import BeautifulSoup
        
        enriched = []
        for i, job in enumerate(jobs):
            try:
                print(f"Fetching description {i+1}/{len(jobs)}: {job['title']} at {job['company']}")
                
                html = self._scrape_url(job["url"])
