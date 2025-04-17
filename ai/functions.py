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



import re
from collections import Counter

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