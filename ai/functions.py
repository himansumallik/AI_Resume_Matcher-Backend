import datetime
import spacy
import PyPDF2
import re
from collections import Counter
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

nlp = spacy.load("en_core_web_sm")






def get_db_connection():
    """Establishes a database connection using environment variables."""
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )






def extract_text_from_pdf(pdf_path):
    """Extracts text content from a PDF file."""
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
    except FileNotFoundError:
        print(f"Error: PDF file not found at {pdf_path}")
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
    return text






def extract_keywords(text, max_keywords=20):
    """Extracts and filters meaningful keywords from the given text."""
    words = re.findall(r'\b\w+\b', text.lower())
    stop_words = {
        'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours',
        'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
        'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves',
        'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are',
        'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does',
        'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until',
        'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into',
        'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down',
        'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here',
        'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more',
        'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
        'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now'
    }

    filtered_words = [
        word for word in words
        if len(word) > 3 and word not in stop_words and not word.isdigit()
    ]

    word_counts = Counter(filtered_words)
    top_keywords = [word for word, _ in word_counts.most_common(max_keywords)]

    return top_keywords






def calculate_match(resume_text, job_desc):
    """Calculates the match percentage between resume and job description."""
    resume_doc = nlp(resume_text.lower())
    job_doc = nlp(job_desc.lower())

    resume_tokens = set([token.lemma_ for token in resume_doc if token.is_alpha])
    job_tokens = set([token.lemma_ for token in job_doc if token.is_alpha])

    matched = resume_tokens.intersection(job_tokens)
    match_percent = round(len(matched) / len(job_tokens) * 100, 2) if job_tokens else 0
    missing_keywords = list(job_tokens - resume_tokens)

    return match_percent, missing_keywords







def filter_job_keywords(keywords):
    """Filters out common words and keeps job-relevant terms (less aggressive filtering)."""
    common_words = {
        'a', 'an', 'the', 'and', 'or', 'but', 'of', 'at', 'by', 'for',
        'in', 'on', 'to', 'with', 'we', 'she', 'he', 'it', 'they', 'them',
        'his', 'her', 'their', 'our', 'your', 'my', 'this', 'that', 'these',
        'those', 'is', 'are', 'was', 'were', 'be', 'being', 'been', 'have',
        'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could',
        'can', 'may', 'might', 'must', 'shall'
    }
    job_related = [
        word for word in keywords
        if (len(word) > 2 and  # Reduced minimum length
            word.lower() not in common_words and
            (word[0].isupper() or word.isupper()))  # Keep proper nouns and acronyms
    ]
    return job_related






def suggest_related_skills(keywords):
    """Suggests related technical skills based on given keywords."""
    skill_mappings = {
        'python': ['Django', 'Flask', 'Pandas', 'NumPy', 'PyTorch'],
        'java': ['Spring', 'Hibernate', 'J2EE', 'Android'],
        'javascript': ['React', 'Node.js', 'Vue', 'Angular'],
        'machine learning': ['TensorFlow', 'Keras', 'scikit-learn', 'AI'],
        'database': ['SQL', 'MySQL', 'PostgreSQL', 'MongoDB'],
        'cloud': ['AWS', 'Azure', 'GCP', 'Docker', 'Kubernetes'],
        'data': ['Data Analysis', 'Data Mining', 'Big Data'],
        'develop': ['Software Development', 'Web Development', 'Mobile Development'],
        'manage': ['Project Management', 'Team Management', 'Product Management'],
        'analyze': ['Business Analysis', 'Statistical Analysis'],
        'design': ['UI Design', 'UX Design', 'Graphic Design'],
        'network': ['Network Administration', 'Network Security'],
        'security': ['Cybersecurity', 'Information Security'],
        'test': ['Software Testing', 'QA Testing']
    }

    suggestions = []
    seen = set()

    for keyword in keywords:
        keyword = keyword.lower()
        for base_skill, related_skills in skill_mappings.items():
            if base_skill in keyword and base_skill not in seen:
                for skill in related_skills:
                    if skill not in seen:
                        suggestions.append(skill)
                        seen.add(skill)
                seen.add(base_skill)

    return suggestions[:10]



def extract_strengths(text):
    common_strengths = [
        "team player", "fast learner", "adaptability", "communication",
        "problem solving", "leadership", "time management", "detail-oriented"
    ]
    found = [s for s in common_strengths if s in text.lower()]
    return list(set(found))[:5]



def calculate_score(suggestions):
    """Calculate resume score (0-100) based on suggestions"""
    critical = sum(1 for s in suggestions if s['priority'] == 'high')
    warnings = sum(1 for s in suggestions if s['priority'] == 'medium')
    
    score = 100
    score -= critical * 10  # -10 points per critical issue
    score -= warnings * 5   # -5 points per warning
    return max(0, min(100, score))



def estimate_experience(text):
    """Estimates years of experience from resume text."""
    import re
    from datetime import datetime

    year_pattern = r'(\d+)\s*(years?|yrs?)'
    duration_pattern = r'(20\d{2})\s*[-–]\s*(20\d{2}|present|now)'

    year_matches = re.findall(year_pattern, text.lower())
    duration_matches = re.findall(duration_pattern, text.lower())

    total_years = 0

    for match in year_matches:
        try:
            total_years += int(match[0])
        except:
            pass

    for match in duration_matches:
        try:
            start_year = int(match[0])
            end_year = datetime.now().year if match[1] in ['present', 'now'] else int(match[1])
            total_years += (end_year - start_year)
        except:
            pass

    # Use a simple average if duration_matches found, else just cap the total years
    if duration_matches:
        estimated_years = total_years // max(1, len(duration_matches))
    else:
        estimated_years = total_years

    return min(estimated_years, 15)  # Cap at 15 years

def estimate_required_experience(job_desc):
    """Estimates required years from job description."""
    patterns = [
        r'(\d+)\+?\s*years?\s*experience',
        r'experience\s*of\s*(\d+)\+?\s*years?',
        r'(\d+)\s*-\s*(\d+)\s*years?\s*experience'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, job_desc.lower())
        if matches:
            if isinstance(matches[0], tuple):  # For ranges like "3-5 years"
                return int(matches[0][1])  # Take the upper bound
            return int(matches[0])  # Take single number
    
    return 3  # Default if not specified

def calculate_ats_score(resume_text):
    """Calculates ATS compatibility score (0-100)."""
    checks = {
        'has_contact_info': bool(re.search(r'(\b[\w\.-]+@[\w\.-]+\.\w{2,4}\b)|(\b\d{3}[-.]?\d{3}[-.]?\d{4}\b)', resume_text)),
        'has_work_history': bool(re.search(r'(experience|work history|employment)', resume_text, re.I)),
        'has_education': bool(re.search(r'(education|academic background|qualifications)', resume_text, re.I)),
        'has_skills': bool(re.search(r'(skills|technical skills|competencies)', resume_text, re.I)),
        'proper_headings': len(re.findall(r'^\s*[A-Z][A-Za-z ]+:\s*$', resume_text, re.M)) >= 3
    }
    
    return round(sum(checks.values()) / len(checks) * 100)

def check_ats_issues(resume_text):
    """Identifies potential ATS issues."""
    issues = []
    
    if not re.search(r'^\s*[A-Z][A-Za-z ]+:\s*$', resume_text, re.M):
        issues.append("Consider using standard section headings (e.g., 'Experience:', 'Education:')")
    
    if len(resume_text.split()) > 800:
        issues.append("Resume might be too long (consider keeping under 2 pages)")
    
    if re.search(r'columns?|tables?|graphics?|images?', resume_text, re.I):
        issues.append("Avoid using columns/tables/graphics as they may confuse ATS")
    
    return issues

def generate_suggestions(missing_keywords, exp_years, req_years, resume_text):
    """Generates improvement suggestions."""
    suggestions = []
    
    if missing_keywords:
        suggestions.append(f"Add these keywords to your resume: {', '.join(missing_keywords[:5])}")
    
    if exp_years < req_years:
        suggestions.append(f"Highlight transferable skills to compensate for experience gap ({exp_years} vs {req_years} years)")
    
    if not re.search(r'\bachievements?\b|\baccomplishments?\b', resume_text, re.I):
        suggestions.append("Add an 'Achievements' section with quantifiable results")
    
    if len(re.findall(r'\bincreased\b|\bimproved\b|\breduced\b|\bsaved\b', resume_text, re.I)) < 3:
        suggestions.append("Include more measurable achievements (e.g., 'Increased sales by 30%')")
    
    return suggestions[:5]