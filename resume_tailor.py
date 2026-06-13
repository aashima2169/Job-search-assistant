import google.generativeai as genai
import json
import os
from typing import Dict, List

class ResumeTailor:
    """Suggest resume changes to better fit a specific job"""
    
    def __init__(self, api_key=None):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
    
    def suggest_tailoring(self, resume_data: Dict, job: Dict, score_data: Dict) -> Dict:
        """
        Given a resume, a JD, and the score breakdown,
        suggest specific changes to improve fitment.
        
        Returns:
        {
            "worth_tailoring": true/false,
            "effort_level": "low/medium/high",
            "summary_rewrite": "New summary targeting this role...",
            "skills_to_highlight": ["skill1", "skill2"],
            "skills_to_add_if_true": ["skill3"],  # only if candidate actually has them
            "experience_bullets_to_rewrite": [
                {
                    "company": "XYZ",
                    "original": "Managed team of 5",
                    "suggested": "Led cross-functional team of 5 to deliver X, reducing Y by Z%"
                }
            ],
            "keywords_missing": ["keyword1", "keyword2"],
            "what_not_to_change": "Your MBA and fintech experience are already strong signals"
        }
        """
        
        prompt = f"""
You are a resume coach. A candidate has a {score_data.get('overall_score')}/100 fitment score 
for a job. Suggest SPECIFIC, HONEST changes to improve their resume for this role.

CANDIDATE RESUME:
{json.dumps(resume_data, indent=2)}

JOB DESCRIPTION:
Title: {job.get('title')}
Company: {job.get('company')}
Description: {job.get('description')}

CURRENT SCORE GAPS:
{json.dumps(score_data.get('gaps', []), indent=2)}
Missing keywords or signals: {json.dumps(score_data.get('gaps', []))}

Rules:
- NEVER suggest adding skills the candidate doesn't have
- Only suggest REFRAMING existing experience, not fabricating
- Be specific — quote actual bullet points and suggest rewrites
- If score is already 85+, say worth_tailoring = false
- Identify ATS keywords from the JD that are missing from resume

Return ONLY valid JSON:
{{
    "worth_tailoring": true/false,
    "effort_level": "low|medium|high",
    "summary_rewrite": "Suggested new summary or null",
    "skills_to_highlight": ["existing skills to move to top"],
    "skills_to_add_if_true": ["skills to add only if candidate has them"],
    "experience_bullets_to_rewrite": [
        {{
            "company": "company name",
            "original": "original bullet",
            "suggested": "rewritten bullet with metrics and keywords"
        }}
    ],
    "keywords_missing": ["ATS keywords from JD not in resume"],
    "what_not_to_change": "What's already strong for this role"
}}
"""
        response = self.model.generate_content(prompt)
        return self._parse_json(response.text)
    
    def _parse_json(self, text: str) -> Dict:
        start = text.find('{')
        end = text.rfind('}') + 1
        return json.loads(text[start:end])
