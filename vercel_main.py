from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Dict, List, Optional
import os
import json
import logging
from io import BytesIO

from supabase import create_client, Client
from resume_processor import ResumeExtractor, ResumeParser, ResumeMatcher
from platform_config_loader import PlatformConfigLoader
# from platform_handlers import PlatformHandlerFactory

app = FastAPI(title="Push - Resume-Based Job Matching (Vercel)")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize components
resume_extractor = ResumeExtractor()
resume_parser = ResumeParser()
resume_matcher = ResumeMatcher()
loader = PlatformConfigLoader()


# ============ SCHEMAS ============

class JobScore(BaseModel):
    """Detailed job score breakdown"""
    job_title: str
    company: str
    location: str
    salary: Optional[str]
    overall_score: int
    recommendation: str
    scores: Dict[str, int]
    strengths: List[str]
    gaps: List[str]
    red_flags: List[str]
    reasoning: str


class MatchJobsRequest(BaseModel):
    """Request to match jobs using uploaded resume"""
    platform: str
    resume_id: str
    job_search_keyword: str
    job_search_location: str


class MatchJobsResponse(BaseModel):
    """Response with scored jobs"""
    platform: str
    resume_id: str
    candidate_name: str
    candidate_title: str
    total_jobs_found: int
    scored_jobs_count: int
    jobs: List[JobScore]
    summary: Dict


# ============ RESUME UPLOAD ============

@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...), user_id: str = "default", keep_history: bool = True):
    """
    Upload or update resume to Supabase Storage
    
    Args:
        file: PDF resume file
        user_id: User identifier (for organizing resumes)
        keep_history: If True, keep old versions; if False, replace
    
    Returns:
        resume_id for use in job matching
    """
    try:
        # Validate file type
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported"
            )
        
        logger.info(f"Uploading resume: {file.filename}")
        
        # Read file into memory
        file_content = await file.read()
        
        # Extract text from PDF (in memory)
        logger.info("Extracting text from PDF...")
        resume_text = extract_pdf_text(file_content)
        
        # Parse resume using Gemini
        logger.info("Parsing resume with Gemini...")
        resume_data = resume_parser.parse_resume(resume_text)
        
        # Check if this resume already exists
        base_name = file.filename.replace(".pdf", "").lower().replace(" ", "_")
        existing_response = supabase.table("resumes").select("*").eq("user_id", user_id).eq("base_name", base_name).execute()
        
        version = 1
        if existing_response.data and keep_history:
            # Find highest version
            versions = [r.get("version", 1) for r in existing_response.data]
            version = max(versions) + 1
            logger.info(f"Found existing resume. Creating version {version}")
        elif existing_response.data and not keep_history:
            # Delete old versions
            logger.info("Deleting old resume versions...")
            for old_resume in existing_response.data:
                supabase.table("resumes").delete().eq("id", old_resume["id"]).execute()
                if old_resume.get("storage_path"):
                    try:
                        supabase.storage.from_("resumes").remove([old_resume["storage_path"]])
                    except:
                        pass
            version = 1
        
        # Upload PDF to Supabase Storage with version
        storage_path = f"{user_id}/{base_name}_v{version}.pdf"
        
        logger.info(f"Uploading to Supabase Storage: {storage_path}")
        supabase.storage.from_("resumes").upload(
            path=storage_path,
            file=BytesIO(file_content),
            file_options={"content-type": "application/pdf"}
        )
        
        # Save metadata to database
        logger.info("Saving metadata to database...")
        resume_record = {
            "user_id": user_id,
            "filename": file.filename,
            "base_name": base_name,
            "version": version,
            "storage_path": storage_path,
            "parsed_data": resume_data,
            "is_active": True  # Mark as active version
        }
        
        # If this is not the first version, deactivate old versions
        if version > 1:
            supabase.table("resumes").update({"is_active": False}).eq("user_id", user_id).eq("base_name", base_name).execute()
        
        db_response = supabase.table("resumes").insert(resume_record).execute()
        
        if not db_response.data:
            raise Exception("Failed to save resume metadata to database")
        
        db_id = db_response.data[0]["id"]
        
        logger.info(f"✅ Resume uploaded and parsed: {base_name} (v{version})")
        
        return {
            "status": "success",
            "resume_id": db_id,
            "version": version,
            "filename": file.filename,
            "candidate_name": resume_data.get("name"),
            "candidate_title": resume_data.get("current_title"),
            "years_experience": resume_data.get("years_of_experience"),
            "location": resume_data.get("location"),
            "skills": resume_data.get("technical_skills", [])[:10],
            "message": f"✅ Resume v{version} uploaded. Use resume_id '{db_id}' for job matching"
        }
    
    except Exception as e:
        logger.error(f"Error uploading resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/resume/{resume_id}")
async def get_resume_info(resume_id: str):
    """Get details of a parsed resume"""
    try:
        response = supabase.table("resumes").select("*").eq("id", resume_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail=f"Resume '{resume_id}' not found")
        
        resume = response.data[0]
        parsed = resume["parsed_data"]
        
        return {
            "resume_id": resume_id,
            "filename": resume["filename"],
            "name": parsed.get("name"),
            "email": parsed.get("email"),
            "phone": parsed.get("phone"),
            "location": parsed.get("location"),
            "current_title": parsed.get("current_title"),
            "years_experience": parsed.get("years_of_experience"),
            "technical_skills": parsed.get("technical_skills", []),
            "soft_skills": parsed.get("soft_skills", []),
            "experience_count": len(parsed.get("experience", [])),
            "education": parsed.get("education", []),
            "certifications": parsed.get("certifications", []),
            "preferences": parsed.get("preferences", {})
        }
    
    except Exception as e:
        logger.error(f"Error fetching resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/resumes")
async def list_resumes(user_id: str = "default"):
    """List all resumes (all versions) for a user"""
    try:
        response = supabase.table("resumes").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        
        resumes = []
        for resume_data in response.data:
            parsed = resume_data["parsed_data"]
            resumes.append({
                "resume_id": resume_data["id"],
                "filename": resume_data["filename"],
                "base_name": resume_data.get("base_name"),
                "version": resume_data.get("version", 1),
                "is_active": resume_data.get("is_active", False),
                "name": parsed.get("name"),
                "current_title": parsed.get("current_title"),
                "location": parsed.get("location"),
                "created_at": resume_data["created_at"]
            })
        
        return {
            "total_resumes": len(resumes),
            "resumes": resumes
        }
    
    except Exception as e:
        logger.error(f"Error listing resumes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/resumes/{base_name}/versions")
async def get_resume_versions(base_name: str, user_id: str = "default"):
    """Get all versions of a specific resume"""
    try:
        response = supabase.table("resumes").select("*").eq("user_id", user_id).eq("base_name", base_name).order("version", desc=True).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail=f"Resume '{base_name}' not found")
        
        versions = []
        for resume_data in response.data:
            parsed = resume_data["parsed_data"]
            versions.append({
                "resume_id": resume_data["id"],
                "version": resume_data.get("version", 1),
                "is_active": resume_data.get("is_active", False),
                "filename": resume_data["filename"],
                "name": parsed.get("name"),
                "created_at": resume_data["created_at"]
            })
        
        return {
            "base_name": base_name,
            "total_versions": len(versions),
            "versions": versions
        }
    
    except Exception as e:
        logger.error(f"Error fetching versions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/resumes/{resume_id}/activate")
async def activate_resume_version(resume_id: str):
    """Set a resume version as active (for job matching)"""
    try:
        # Get the resume to find its base_name and user_id
        response = supabase.table("resumes").select("*").eq("id", resume_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail=f"Resume '{resume_id}' not found")
        
        resume = response.data[0]
        base_name = resume.get("base_name")
        user_id = resume.get("user_id")
        
        # Deactivate all versions of this resume
        supabase.table("resumes").update({"is_active": False}).eq("user_id", user_id).eq("base_name", base_name).execute()
        
        # Activate this version
        supabase.table("resumes").update({"is_active": True}).eq("id", resume_id).execute()
        
        logger.info(f"Activated resume version: {resume_id}")
        
        return {
            "status": "success",
            "message": f"Resume version {resume.get('version', 1)} activated",
            "resume_id": resume_id
        }
    
    except Exception as e:
        logger.error(f"Error activating resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/resumes/{resume_id}")
async def delete_resume_version(resume_id: str):
    """Delete a specific resume version"""
    try:
        # Get the resume
        response = supabase.table("resumes").select("*").eq("id", resume_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail=f"Resume '{resume_id}' not found")
        
        resume = response.data[0]
        storage_path = resume.get("storage_path")
        
        # Delete from storage
        if storage_path:
            try:
                supabase.storage.from_("resumes").remove([storage_path])
                logger.info(f"Deleted from storage: {storage_path}")
            except Exception as e:
                logger.warning(f"Could not delete from storage: {str(e)}")
        
        # Delete from database
        supabase.table("resumes").delete().eq("id", resume_id).execute()
        
        logger.info(f"Deleted resume version: {resume_id}")
        
        return {
            "status": "success",
            "message": f"Resume version {resume.get('version', 1)} deleted"
        }
    
    except Exception as e:
        logger.error(f"Error deleting resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ JOB MATCHING ============

@app.post("/match-jobs-with-resume", response_model=MatchJobsResponse)
async def match_jobs_with_resume(request: MatchJobsRequest):
    """
    Match and score jobs against uploaded resume
    """
    try:
        # Get resume from database
        logger.info(f"Fetching resume: {request.resume_id}")
        response = supabase.table("resumes").select("parsed_data").eq("id", request.resume_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Resume '{request.resume_id}' not found"
            )
        
        resume_data = response.data[0]["parsed_data"]
        
        logger.info("Starting job matching...")
        
        # Get platform handler
       # platform_handler = PlatformHandlerFactory.get_handler(request.platform, loader)
        
        # Build job search URL
        config = platform_handler.config
        job_search_url = config.jobs_url_pattern.format(
            keyword=request.job_search_keyword,
            location=request.job_search_location
        )
        
        # Extract jobs
        logger.info("🔍 Scraping job listings...")
        jobs = platform_handler.extract_jobs(job_search_url)
        
        if not jobs:
            return MatchJobsResponse(
                platform=request.platform,
                resume_id=request.resume_id,
                candidate_name=resume_data.get("name", "Unknown"),
                candidate_title=resume_data.get("current_title", "Unknown"),
                total_jobs_found=0,
                scored_jobs_count=0,
                jobs=[],
                summary={}
            )
        
        # Score jobs
        logger.info(f"🤖 Scoring {len(jobs)} jobs...")
        scored_jobs = []
        
        for job in jobs:
            try:
                score = resume_matcher.score_job(resume_data, job)
                scored_jobs.append(JobScore(**score))
            except Exception as e:
                logger.warning(f"Failed to score job: {str(e)}")
                continue
        
        # Sort by score
        scored_jobs.sort(key=lambda x: x.overall_score, reverse=True)
        
        # Calculate summary
        if scored_jobs:
            scores = [job.overall_score for job in scored_jobs]
            summary = {
                "avg_score": round(sum(scores) / len(scores)),
                "max_score": max(scores),
                "min_score": min(scores),
                "apply_count": len([j for j in scored_jobs if j.recommendation == "APPLY"]),
                "consider_count": len([j for j in scored_jobs if j.recommendation == "CONSIDER"]),
                "skip_count": len([j for j in scored_jobs if j.recommendation == "SKIP"])
            }
        else:
            summary = {}
        
        logger.info(f"✅ Matched {len(scored_jobs)} jobs")
        
        return MatchJobsResponse(
            platform=request.platform,
            resume_id=request.resume_id,
            candidate_name=resume_data.get("name", "Unknown"),
            candidate_title=resume_data.get("current_title", "Unknown"),
            total_jobs_found=len(jobs),
            scored_jobs_count=len(scored_jobs),
            jobs=scored_jobs,
            summary=summary
        )
    
    except Exception as e:
        logger.error(f"Error matching jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ HELPER FUNCTIONS ============

def extract_pdf_text(file_content: bytes) -> str:
    """Extract text from PDF bytes (in memory)"""
    import PyPDF2
    from io import BytesIO
    
    try:
        pdf_file = BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        
        for page in pdf_reader.pages:
            text += page.extract_text()
        
        if not text.strip():
            raise ValueError("PDF appears empty or needs OCR")
        
        return text
    
    except Exception as e:
        raise Exception(f"Failed to extract PDF: {str(e)}")


# ============ HEALTH CHECK ============

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "Push - Resume Job Matcher (Vercel)",
        "storage": "Supabase"
    }
from mangum import Mangum
handler = Mangum(app)
