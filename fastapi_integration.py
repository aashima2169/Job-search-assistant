from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Optional
from platform_config_loader import PlatformConfigLoader
from platform_handlers import PlatformHandlerFactory
import logging

app = FastAPI(title="Push - Platform Handler API")
loader = PlatformConfigLoader()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============ SCHEMAS ============

class ProfileExtractionRequest(BaseModel):
    """Request to extract profile data from a URL"""
    platform: str
    profile_url: str


class ProfileExtractionResponse(BaseModel):
    """Response with extracted profile data"""
    platform: str
    url: str
    data: Dict
    status: str


class PlatformInfo(BaseModel):
    """Basic platform information"""
    key: str
    name: str
    enabled: bool
    scraper_type: str


class AddPlatformRequest(BaseModel):
    """Request to add a new platform"""
    platform_key: str
    name: str
    base_url: str
    profile_url_pattern: str
    scraper_type: str
    timeout: int
    selectors: Dict[str, str]
    metadata: Optional[Dict] = None


# ============ ENDPOINTS ============

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "platforms_available": loader.get_enabled_platforms(),
        "total_platforms": len(loader.platforms)
    }


@app.get("/platforms", response_model=List[PlatformInfo])
def list_platforms():
    """List all available platforms"""
    platforms = []
    for key, config in loader.platforms.items():
        platforms.append(PlatformInfo(
            key=key,
            name=config.name,
            enabled=config.enabled,
            scraper_type=config.scraper_type
        ))
    return platforms


@app.get("/platforms/{platform_key}")
def get_platform_info(platform_key: str):
    """Get detailed info about a specific platform"""
    config = loader.get_platform(platform_key)
    if not config:
        raise HTTPException(status_code=404, detail=f"Platform '{platform_key}' not found")
    
    return {
        "key": platform_key,
        "name": config.name,
        "base_url": config.base_url,
        "profile_url_pattern": config.profile_url_pattern,
        "enabled": config.enabled,
        "scraper_type": config.scraper_type,
        "timeout": config.timeout,
        "selectors": config.selectors,
        "requires_auth": config.requires_auth,
        "metadata": config.metadata
    }


@app.post("/extract-profile", response_model=ProfileExtractionResponse)
async def extract_profile(request: ProfileExtractionRequest):
    """Extract profile data from given URL"""
    try:
        # Get handler for platform
        handler = PlatformHandlerFactory.get_handler(request.platform, loader)
        
        # Validate URL belongs to platform
        if not handler.validate_url(request.profile_url):
            raise HTTPException(
                status_code=400,
                detail=f"URL does not belong to {request.platform} platform"
            )
        
        # Extract profile data
        logger.info(f"Extracting {request.platform} profile: {request.profile_url}")
        profile_data = handler.extract_profile_data(request.profile_url)
        
        return ProfileExtractionResponse(
            platform=request.platform,
            url=request.profile_url,
            data=profile_data.get("data", {}),
            status="success"
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error extracting profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error extracting profile: {str(e)}")


@app.post("/platforms")
async def add_platform(request: AddPlatformRequest):
    """Add a new platform to the config"""
    try:
        new_platform = {
            "name": request.name,
            "base_url": request.base_url,
            "profile_url_pattern": request.profile_url_pattern,
            "enabled": True,
            "scraper_type": request.scraper_type,
            "timeout": request.timeout,
            "selectors": request.selectors,
            "api_method": "none",
            "requires_auth": False,
            "metadata": request.metadata or {"description": f"{request.name} profile scraping"}
        }
        
        loader.add_platform(request.platform_key, new_platform)
        
        return {
            "status": "success",
            "message": f"Platform '{request.platform_key}' added successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding platform: {str(e)}")


@app.put("/platforms/{platform_key}")
async def update_platform(platform_key: str, updates: Dict):
    """Update an existing platform config"""
    try:
        loader.update_platform(platform_key, updates)
        
        return {
            "status": "success",
            "message": f"Platform '{platform_key}' updated successfully"
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating platform: {str(e)}")


@app.patch("/platforms/{platform_key}/enable")
async def enable_platform(platform_key: str):
    """Enable a platform"""
    try:
        loader.enable_platform(platform_key)
        return {
            "status": "success",
            "message": f"Platform '{platform_key}' enabled"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/platforms/{platform_key}/disable")
async def disable_platform(platform_key: str):
    """Disable a platform"""
    try:
        loader.disable_platform(platform_key)
        return {
            "status": "success",
            "message": f"Platform '{platform_key}' disabled"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/platforms/{platform_key}/validate-url")
async def validate_url(platform_key: str, url: str):
    """Validate if URL belongs to a platform"""
    try:
        handler = PlatformHandlerFactory.get_handler(platform_key, loader)
        is_valid = handler.validate_url(url)
        
        return {
            "platform": platform_key,
            "url": url,
            "is_valid": is_valid
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ EXAMPLE USAGE ============

"""
# Start server
uvicorn main:app --reload

# Test endpoints:

# 1. List all platforms
curl http://localhost:8000/platforms

# 2. Get specific platform info
curl http://localhost:8000/platforms/linkedin

# 3. Extract profile
curl -X POST http://localhost:8000/extract-profile \
  -H "Content-Type: application/json" \
  -d '{"platform": "linkedin", "profile_url": "https://linkedin.com/in/username"}'

# 4. Add new platform
curl -X POST http://localhost:8000/platforms \
  -H "Content-Type: application/json" \
  -d '{
    "platform_key": "twitter",
    "name": "Twitter",
    "base_url": "https://twitter.com",
    "profile_url_pattern": "https://twitter.com/{username}",
    "scraper_type": "http",
    "timeout": 10,
    "selectors": {"name": "h2.ProfileCard-title", "bio": "p.ProfileCard-bio"}
  }'

# 5. Enable/Disable platform
curl -X PATCH http://localhost:8000/platforms/linkedin/disable

# 6. Validate URL
curl http://localhost:8000/platforms/linkedin/validate-url?url=https://linkedin.com/in/test
"""
