from flask import Flask, request, jsonify
import spacy
import PyPDF2
import os
import psycopg2
from flask_cors import CORS
from dotenv import load_dotenv
import os
import tempfile
from PyPDF2 import PdfReader  
from models import db, Resume  
import re
from collections import Counter

load_dotenv()  # Automatically reads from .env file

app = Flask(__name__)
CORS(app)
nlp = spacy.load("en_core_web_sm")


app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:7448596@localhost/resume_matcher'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()  # This will create the resumes table if it doesn't exist

# Ensure there's an upload folder to save files temporarily
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER



def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )




def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text


def extract_keywords(text):
    """Extract and filter meaningful keywords from text"""
    # Remove punctuation and convert to lowercase
    words = re.findall(r'\b\w+\b', text.lower())
    
    # Common words to exclude (expand this list as needed)
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
    
    # Keep only meaningful words
    keywords = [
        word for word in words 
        if (len(word) > 3 and 
            word not in stop_words and
            not word.isdigit())
    ]
    
    # Get most common keywords
    return [word for word, count in Counter(keywords).most_common(20)]


def calculate_match(resume_text, job_desc):
    resume_doc = nlp(resume_text.lower())
    job_doc = nlp(job_desc.lower())

    resume_tokens = set([token.lemma_ for token in resume_doc if token.is_alpha])
    job_tokens = set([token.lemma_ for token in job_doc if token.is_alpha])

    matched = resume_tokens.intersection(job_tokens)
    match_percent = round(len(matched) / len(job_tokens) * 100, 2) if job_tokens else 0
    missing_keywords = list(job_tokens - resume_tokens)

    return match_percent, missing_keywords





@app.route('/analyze', methods=['POST'])
def analyze_resume():
    try:
        # [Previous file handling code remains the same...]
        
        resume_text = extract_text_from_pdf(resume_path)
        
        # Extract and filter keywords from both documents
        resume_keywords = extract_keywords(resume_text)
        job_keywords = extract_keywords(job_desc)
        
        # Calculate match percentage
        matched = set(resume_keywords) & set(job_keywords)
        match_percent = round(len(matched) / len(job_keywords) * 100, 2) if job_keywords else 0
        
        # Get missing keywords (only those that appear in job description)
        missing = [kw for kw in job_keywords if kw not in resume_keywords]
        
        # Capitalize keywords for better presentation
        missing_keywords = [kw.capitalize() for kw in missing[:10]]  # Show top 10 missing
        
        return jsonify({
            'matchPercentage': match_percent,
            'missingKeywords': missing_keywords,
            'suggestedSkills': suggest_related_skills(missing)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def filter_job_keywords(keywords):
    """Filter out common words and keep job-relevant terms"""
    common_words = {
        'a', 'an', 'the', 'and', 'or', 'but', 'of', 'at', 'by', 'for', 
        'in', 'on', 'to', 'with', 'we', 'she', 'he', 'it', 'they', 'them',
        'his', 'her', 'their', 'our', 'your', 'my', 'this', 'that', 'these',
        'those', 'is', 'are', 'was', 'were', 'be', 'being', 'been', 'have',
        'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could',
        'can', 'may', 'might', 'must', 'shall'
    }
    
    job_related = []
    for word in keywords:
        # Keep only nouns/proper nouns and specific verbs (customize as needed)
        lower_word = word.lower()
        if (len(word) > 3 and 
            lower_word not in common_words and
            word[0].isupper() or word.isupper()):  # Keep proper nouns and acronyms
            job_related.append(word)
    
    return job_related

def suggest_related_skills(keywords):
    """Suggest related technical skills based on missing keywords"""
    skill_mappings = {
        'python': ['Django', 'Flask', 'Pandas', 'NumPy', 'PyTorch'],
        'java': ['Spring', 'Hibernate', 'J2EE', 'Android'],
        'javascript': ['React', 'Node.js', 'Vue', 'Angular'],
        'machine learning': ['TensorFlow', 'Keras', 'scikit-learn', 'AI'],
        'database': ['SQL', 'MySQL', 'PostgreSQL', 'MongoDB'],
        'cloud': ['AWS', 'Azure', 'GCP', 'Docker', 'Kubernetes']
    }
    
    suggestions = set()
    for keyword in keywords:
        lower_key = keyword.lower()
        if lower_key in skill_mappings:
            suggestions.update(skill_mappings[lower_key])
        # Add partial matches (e.g., "data" -> "database" skills)
        for skill, related in skill_mappings.items():
            if skill in lower_key:
                suggestions.update(related)
    
    return list(suggestions)[:10]  # Return top 10 suggestions






@app.route('/recommend', methods=['POST'])
def recommend_jobs():
    if 'resume' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    resume_file = request.files['resume']
    if resume_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Save resume
    resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_file.filename)
    resume_file.save(resume_path)
    resume_text = extract_text_from_pdf(resume_path)

    # Fetch jobs from DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, company, description FROM jobs")
    jobs = cursor.fetchall()
    cursor.close()
    conn.close()

    # Calculate similarity
    resume_doc = nlp(resume_text.lower())
    resume_tokens = set([token.lemma_ for token in resume_doc if token.is_alpha])

    recommendations = []
    for job in jobs:
        job_id, title, company, description = job
        job_doc = nlp(description.lower())
        job_tokens = set([token.lemma_ for token in job_doc if token.is_alpha])
        match = resume_tokens.intersection(job_tokens)
        score = round(len(match) / len(job_tokens) * 100, 2) if job_tokens else 0
        recommendations.append({
            'id': job_id,
            'title': title,
            'company': company,
            'description': description,
            'matchPercentage': score
        })

    # Sort and return top 5
    top_matches = sorted(recommendations, key=lambda x: x['matchPercentage'], reverse=True)[:5]
    return jsonify(top_matches)




@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Save the uploaded file temporarily
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, file.filename)
    file.save(file_path)

    # Extract text (example using PyPDF2 for PDFs)
    text = ''
    if file.filename.lower().endswith('.pdf'):
        try:
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += page.extract_text()
        except Exception as e:
            return jsonify({'error': f'Error reading PDF: {str(e)}'}), 500
    else:
        return jsonify({'error': 'Unsupported file type'}), 400

    # Store resume in database
    new_resume = Resume(name=file.filename, content=text)
    db.session.add(new_resume)
    db.session.commit()

    return jsonify({'message': 'Resume uploaded successfully', 'resume_id': new_resume.id}), 200




@app.route('/format-check', methods=['POST'])
def check_formatting():
    if 'resume' not in request.files:
        return jsonify({'error': 'No resume file uploaded'}), 400

    resume_file = request.files['resume']
    resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_file.filename)
    resume_file.save(resume_path)

    try:
        resume_text = extract_text_from_pdf(resume_path)
        
        suggestions = []

        # Example formatting checks
        if not any(word.lower() in resume_text.lower() for word in ['summary', 'objective']):
            suggestions.append("Consider adding a 'Summary' or 'Objective' section.")
        
        if len(resume_text.split()) < 300:
            suggestions.append("Your resume looks a bit short. Consider elaborating on your projects or experiences.")

        if not any(word.lower() in resume_text.lower() for word in ['education']):
            suggestions.append("Add an 'Education' section with degrees and universities.")

        if not any(word.lower() in resume_text.lower() for word in ['experience', 'work']):
            suggestions.append("Add a 'Work Experience' section detailing your previous roles.")

        if not suggestions:
            suggestions.append("Your resume formatting looks good!")

        return jsonify({'suggestions': suggestions})

    except Exception as e:
        print("Error in format-check:", e)
        return jsonify({'error': 'Failed to analyze resume formatting. Please try again.'}), 500





if __name__ == '__main__':
    app.run(port=5001)
