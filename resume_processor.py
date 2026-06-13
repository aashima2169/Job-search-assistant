import PyPDF2
import google.generativeai as genai
import json
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ResumeExtractor:
    """Extract text from PDF resumes"""
    
    @staticmethod
    def extract_text_from_pdf(file_path: str) -> str:
        """Extract all text from PDF resume"""
        try:
            text = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text()
            
            if not text.strip():
                raise ValueError("PDF appears to be empty or scanned without OCR")
            
            return text
        
        except PyPDF2.utils.PdfReadError as e:
            raise Exception(f"Failed to read PDF: {str(e)}")
        except Exception as e:
            raise Exception(f"Error extracting resume: {str(e)}")


class ResumeParser:
    """Parse resume using Gemini API to extract structured data"""
    
    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
    
    def parse_resume(self, resume_text: str) -> Dict:
        """
        Parse resume text into structured data using Gemini
        
        Returns:
        {
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "123-456-7890",
            "location": "San Francisco, CA",
            "willing_to_relocate": true/false,
            "current_title": "Senior Software Engineer",
            "years_of_experience": 5,
            "skills": ["Python", "Java", "AWS", ...],
            "technical_skills": [...],
            "soft_skills": [...],
            "experience": [
                {
                    "title": "Senior Engineer",
                    "company": "Google",
                    "duration": "2019-Present",
                    "years": 5,
                    "description": "...",
                    "key_achievements": ["...", "..."]
                },
                ...
            ],
            "education": [
                {
                    "degree": "Bachelor of Science",
                    "field": "Computer Science",
                    "school": "UC Berkeley",
                    "year": 2019
                },
                ...
            ],
            "certifications": ["AWS Certified Solutions Architect", ...],
            "preferences": {
                "preferred_roles": ["Backend Engineer", "Technical Lead"],
                "preferred_industries": ["Tech", "Finance"],
                "preferred_company_size": "Large (1000+)",
                "remote_preference": "Hybrid",
                "willing_to_travel": false
            }
        }
        """
        
        prompt = self._build_parse_prompt(resume_text)
        
        try:
            response = self.model.generate_content(prompt)
            parsed_data = self._extract_json(response.text)
            return parsed_data
        
        except Exception as e:
            logger.error(f"Error parsing resume: {str(e)}")
            raise
    
    def _build_parse_prompt(self, resume_text: str) -> str:
        return f"""
You are a resume parser. Extract all relevant information from this resume and return it as JSON.

RESUME TEXT:
{resume_text}

Extract and return ONLY valid JSON (no markdown, no explanation) with this structure:
{{
    "name": "Full name or 'Not found'",
    "email": "Email address or null",
    "phone": "Phone number or null",
    "location": "City, State or Country",
    "willing_to_relocate": true/false (infer from resume or default false),
    "current_title": "Current or most recent job title",
    "years_of_experience": number (total years),
    "skills": ["skill1", "skill2", ...],
    "technical_skills": ["Python", "Java", "AWS", ...],
    "soft_skills": ["Leadership", "Communication", ...],
    "experience": [
        {{
            "title": "Job title",
            "company": "Company name",
            "duration": "Start-End (e.g., 2020-Present)",
            "years": number,
            "description": "Brief description of role",
            "key_achievements": ["Achievement 1", "Achievement 2"]
        }}
    ],
    "education": [
        {{
            "degree": "Bachelor/Master/PhD",
            "field": "Field of study",
            "school": "University name",
            "year": graduation_year
        }}
    ],
    "certifications": ["Cert 1", "Cert 2"],
    "preferences": {{
        "preferred_roles": ["Role 1", "Role 2"],
        "preferred_industries": ["Industry 1", "Industry 2"],
        "preferred_company_size": "Small/Medium/Large/Any",
        "remote_preference": "Full Remote/Hybrid/On-site/Any",
        "willing_to_travel": true/false
    }},
    "summary": "2-3 sentence professional summary"
}}

Guidelines:
- Be thorough but accurate
- If information is not found, use null or empty array
- For years of experience, count from first job to current
- Infer preferences from job history if not explicitly stated
- Skills should be specific (not "programming" but "Python", "Java", etc.)
"""
    
    def _extract_json(self, response_text: str) -> Dict:
        """Extract JSON from response text"""
        try:
            # Find JSON in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_str = response_text[json_start:json_end]
            
            parsed = json.loads(json_str)
            return parsed
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from response: {str(e)}")
            logger.error(f"Response text: {response_text}")
            raise ValueError(f"Invalid JSON response from parser: {str(e)}")


class ResumeMatcher:
    """Match jobs against parsed resume data"""
    
    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
    
    def score_job(self, resume_data: Dict, job: Dict) -> Dict:
        """
        Score a job against resume using 4 criteria + company fit
        
        Returns:
        {
            "overall_score": 85,  # 0-100
            "scores": {
                "skill_match": 90,      # Do they have the required skills?
                "experience_fit": 85,   # Right level of experience?
                "role_alignment": 80,   # Does it fit their career path?
                "location_fit": 95,     # Are they in right location?
                "company_fit": 75       # Company culture & size fit?
            },
            "recommendation": "APPLY",  # APPLY, CONSIDER, SKIP
            "strengths": ["...", "..."],
            "gaps": ["...", "..."],
            "red_flags": ["...", "..."],
            "reasoning": "Detailed explanation..."
        }
        """
        
        prompt = self._build_scoring_prompt(resume_data, job)
        
        try:
            response = self.model.generate_content(prompt)
            result = self._parse_score_response(response.text, job)
            return result
        
        except Exception as e:
            logger.error(f"Error scoring job: {str(e)}")
            raise
    
    def _build_scoring_prompt(self, resume_data: Dict, job: Dict) -> str:
        return f"""
You are a career advisor. Score this job against the candidate's resume.

CANDIDATE RESUME:
Name: {resume_data.get('name', 'Unknown')}
Current Title: {resume_data.get('current_title', 'Unknown')}
Years Experience: {resume_data.get('years_of_experience', 0)}
Location: {resume_data.get('location', 'Unknown')}
Technical Skills: {', '.join(resume_data.get('technical_skills', []))}
Experience: {json.dumps(resume_data.get('experience', []), indent=2)}

JOB POSTING:
Title: {job.get('title', 'Unknown')}
Company: {job.get('company', 'Unknown')}
Location: {job.get('location', 'Unknown')}
Remote: {job.get('remote', 'Unknown')}
Salary: {job.get('salary', 'Not specified')}
Description: {job.get('description', 'No description')}
Company Size: {job.get('company_size', 'Unknown')}
Company Culture: {job.get('company_culture', 'Unknown')}

SCORE EACH CRITERION 0-100:

1. SKILL MATCH (0-100):
   - Do they have required skills?
   - Are they expert, intermediate, or beginner in each?
   - Any critical skill gaps?

2. EXPERIENCE FIT (0-100):
   - Right seniority level?
   - Relevant industry/domain experience?
   - Years of experience requirement met?

3. ROLE ALIGNMENT (0-100):
   - Does this role fit their career progression?
   - Is it a lateral move, growth opportunity, or step back?
   - Does it align with their interests (inferred from history)?

4. LOCATION FIT (0-100):
   - Are they in the right location?
   - Is remote/hybrid acceptable?
   - Would they need to relocate?

5. COMPANY FIT (0-100):
   - Company size (from resume: do they prefer startups or large orgs?)
   - Company culture (toxic red flags? aligned values?)
   - Industry preference match?

Return ONLY this JSON (no markdown, no extra text):
{{
    "overall_score": 0,
    "scores": {{
        "skill_match": 0,
        "experience_fit": 0,
        "role_alignment": 0,
        "location_fit": 0,
        "company_fit": 0
    }},
    "recommendation": "APPLY|CONSIDER|SKIP",
    "strengths": ["strength1", "strength2"],
    "gaps": ["gap1", "gap2"],
    "red_flags": ["flag1", "flag2"],
    "reasoning": "Clear explanation of scoring and fit"
}}

Scoring Rules:
- overall_score = average of the 5 criterion scores (rounded)
- Be harsh on missing required skills
- Be strict on company culture red flags
- Reward alignment with career trajectory
- 90-100: Near perfect fit
- 80-89: Strong fit, apply
- 70-79: Good fit, consider
- 50-69: Possible fit, needs consideration
- 0-49: Poor fit, likely struggle
"""
    
    def _parse_score_response(self, response_text: str, job: Dict) -> Dict:
        """Parse scoring response"""
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_str = response_text[json_start:json_end]
            
            score_data = json.loads(json_str)
            
            # Add job info to result
            return {
                "job_title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "job_url": job.get("url"),
                "salary": job.get("salary"),
                **score_data
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse scoring response: {str(e)}")
            raise ValueError(f"Invalid JSON response from scorer: {str(e)}")


# Example usage
if __name__ == "__main__":
    # Extract resume
    pdf_path = "sample_resume.pdf"
    extractor = ResumeExtractor()
    resume_text = extractor.extract_text_from_pdf(pdf_path)
    
    # Parse resume
    parser = ResumeParser()
    resume_data = parser.parse_resume(resume_text)
    print("📄 Parsed Resume:")
    print(json.dumps(resume_data, indent=2))
    
    # Score a job
    matcher = ResumeMatcher()
    sample_job = {
        "title": "Senior Backend Engineer",
        "company": "Meta",
        "location": "San Francisco, CA",
        "remote": "Hybrid",
        "salary": "$200K - $300K",
        "description": "We seek a senior backend engineer...",
        "company_size": "Large (10000+)",
        "company_culture": "Fast-paced, innovation-focused"
    }
    
    score = matcher.score_job(resume_data, sample_job)
    print("\n🎯 Job Score:")
    print(json.dumps(score, indent=2))
