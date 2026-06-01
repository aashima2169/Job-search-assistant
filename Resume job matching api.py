from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
import os
import shutil
from pathlib import Path
import logging

from resume_processor import ResumeExtractor, ResumeParser, ResumeMatcher
from platform_config_loader import PlatformConfigLoader
from platform_handlers import PlatformHandlerFactory

app = FastAPI(title="Push - Resume-Based Job Matching")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize components
loader = PlatformConfigLoader()
resume_extractor = ResumeExtractor()
resume_parser = ResumeParser()
resume_matcher = ResumeMatcher()

# Store parsed resumes in memory (in production, use database)
stored_resumes = {}


# ============ SCHEMAS ============

class JobScore(BaseModel):
    """Detailed job score breakdown"""
    job_title: str
    company: str
    location: str
    salary: Optional[str]
    overall_score: int  # 0-100
    recommendation: str  # APPLY, CONSIDER, SKIP
    scores: Dict[str, int]  # skill_match, experience_fit, role_alignment, location_fit, company_fit
    strengths: List[str]
    gaps: List[str]
    red_flags: List[str]
    reasoning: str


class MatchJobsRequest(BaseModel):
    """Request to match jobs using uploaded resume"""
    platform: str
    resume_id: str  # ID of uploaded resume
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
    summary: Dict  # Stats about scores


# ============ RESUME UPLOAD ENDPOINTS ============

@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    Upload and parse a resume PDF
    
    Returns: resume_id for use in job matching
    """
    try:
        # Validate file type
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported"
            )
        
        # Save file
        file_path = UPLOAD_DIR / f"{file.filename}"
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        
        logger.info(f"Saved resume: {file_path}")
        
        # Extract text from PDF
        logger.info("Extracting text from PDF...")
        resume_text = resume_extractor.extract_text_from_pdf(str(file_path))
        
        # Parse resume using Gemini
        logger.info("Parsing resume...")
        resume_data = resume_parser.parse_resume(resume_text)
        
        # Generate resume ID
        resume_id = file.filename.replace(".pdf", "").lower().replace(" ", "_")
        
        # Store resume
        stored_resumes[resume_id] = {
            "filename": file.filename,
            "file_path": str(file_path),
            "raw_text": resume_text,
            "parsed_data": resume_data,
            "uploaded_at": str(os.path.getmtime(file_path))
        }
        
        logger.info(f"Resume parsed successfully: {resume_id}")
        
        return {
            "status": "success",
            "resume_id": resume_id,
            "filename": file.filename,
            "candidate_name": resume_data.get("name"),
            "candidate_title": resume_data.get("current_title"),
            "years_experience": resume_data.get("years_of_experience"),
            "location": resume_data.get("location"),
            "skills": resume_data.get("technical_skills", [])[:10],  # Top 10 skills
            "message": f"✅ Resume uploaded and parsed. Use resume_id '{resume_id}' for job matching"
        }
    
    except Exception as e:
        logger.error(f"Error uploading resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/resume/{resume_id}")
async def get_resume_info(resume_id: str):
    """Get details of a parsed resume"""
    if resume_id not in stored_resumes:
        raise HTTPException(status_code=404, detail=f"Resume '{resume_id}' not found")
    
    resume = stored_resumes[resume_id]
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


@app.get("/resumes")
async def list_resumes():
    """List all uploaded resumes"""
    resumes = []
    for resume_id, resume_data in stored_resumes.items():
        parsed = resume_data["parsed_data"]
        resumes.append({
            "resume_id": resume_id,
            "filename": resume_data["filename"],
            "name": parsed.get("name"),
            "current_title": parsed.get("current_title"),
            "location": parsed.get("location")
        })
    
    return {
        "total_resumes": len(resumes),
        "resumes": resumes
    }


# ============ JOB MATCHING ENDPOINTS ============

@app.post("/match-jobs-with-resume", response_model=MatchJobsResponse)
async def match_jobs_with_resume(request: MatchJobsRequest):
    """
    Match and score jobs against uploaded resume
    
    Process:
    1. Get parsed resume
    2. Extract job listings
    3. Score each job (0-100) against resume
    4. Return sorted by score
    """
    try:
        # Validate resume exists
        if request.resume_id not in stored_resumes:
            raise HTTPException(
                status_code=404,
                detail=f"Resume '{request.resume_id}' not found. Upload a resume first."
            )
        
        resume_data = stored_resumes[request.resume_id]["parsed_data"]
        
        logger.info(f"Starting job matching for {request.resume_id}...")
        
        # Get platform handler
        platform_handler = PlatformHandlerFactory.get_handler(request.platform, loader)
        
        # Build job search URL
        config = platform_handler.config
        job_search_url = config.jobs_url_pattern.format(
            keyword=request.job_search_keyword,
            location=request.job_search_location
        )
        
        # Extract job listings
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
        
        # Score each job
        logger.info(f"🤖 Scoring {len(jobs)} jobs...")
        scored_jobs = []
        
        for job in jobs:
            try:
                score = resume_matcher.score_job(resume_data, job)
                scored_jobs.append(JobScore(**score))
            except Exception as e:
                logger.warning(f"Failed to score job {job.get('title')}: {str(e)}")
                continue
        
        # Sort by score (highest first)
        scored_jobs.sort(key=lambda x: x.overall_score, reverse=True)
        
        # Calculate summary statistics
        if scored_jobs:
            scores = [job.overall_score for job in scored_jobs]
            summary = {
                "avg_score": round(sum(scores) / len(scores)),
                "max_score": max(scores),
                "min_score": min(scores),
                "apply_count": len([j for j in scored_jobs if j.recommendation == "APPLY"]),
                "consider_count": len([j for j in scored_jobs if j.recommendation == "CONSIDER"]),
                "skip_count": len([j for j in scored_jobs if j.recommendation == "SKIP"]),
                "top_score": scored_jobs[0].overall_score if scored_jobs else 0
            }
        else:
            summary = {}
        
        logger.info(f"✅ Scored {len(scored_jobs)} jobs")
        
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


# ============ HELPER ENDPOINTS ============

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "Push - Resume-Based Job Matcher",
        "resumes_stored": len(stored_resumes)
    }


# ============ USAGE EXAMPLES ============

"""
API WORKFLOW:

1. UPLOAD RESUME
   POST /upload-resume
   Form data: file (PDF)
   
   curl -X POST http://localhost:8000/upload-resume \
     -F "file=@resume.pdf"
   
   Response:
   {
     "status": "success",
     "resume_id": "john_doe_resume",
     "candidate_name": "John Doe",
     "candidate_title": "Senior Software Engineer"
   }

2. MATCH JOBS WITH RESUME
   POST /match-jobs-with-resume
   
   curl -X POST http://localhost:8000/match-jobs-with-resume \
     -H "Content-Type: application/json" \
     -d '{
       "platform": "linkedin",
       "resume_id": "john_doe_resume",
       "job_search_keyword": "senior engineer",
       "job_search_location": "San Francisco"
     }'
   
   Response:
   {
     "platform": "linkedin",
     "resume_id": "john_doe_resume",
     "candidate_name": "John Doe",
     "total_jobs_found": 142,
     "scored_jobs_count": 87,
     "summary": {
       "avg_score": 72,
       "apply_count": 23,
       "consider_count": 45,
       "skip_count": 19
     },
     "jobs": [
       {
         "job_title": "Senior Backend Engineer",
         "company": "Meta",
         "location": "San Francisco, CA",
         "salary": "$200K - $300K",
         "overall_score": 92,
         "recommendation": "APPLY",
         "scores": {
           "skill_match": 95,
           "experience_fit": 90,
           "role_alignment": 88,
           "location_fit": 100,
           "company_fit": 85
         },
         "strengths": [
           "Expert-level match on required skills",
           "Exact experience level and domain"
         ],
         "gaps": ["Never led a team of 20+"],
         "red_flags": [],
         "reasoning": "..."
       }
     ]
   }

3. GET RESUME INFO
   GET /resume/{resume_id}
   
4. LIST ALL RESUMES
   GET /resumes
"""
