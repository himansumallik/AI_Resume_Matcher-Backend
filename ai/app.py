from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from models import db, Resume
import spacy
import os
import tempfile
from collections import Counter
import re
import functions  # Import the functions module
from gpt_model import evaluate_resume_against_job

load_dotenv()

app = Flask(__name__)
CORS(app)
nlp = spacy.load("en_core_web_sm")

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", 'postgresql://postgres:7448596@localhost/resume_matcher')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

# Upload Folder Configuration
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def handle_file_upload(request_files, field_name, upload_dir):
    """Handles file upload and returns the file path."""
    if field_name not in request_files:
        return None, jsonify({'error': f'No file part in {field_name}'}), 400

    file = request_files[field_name]
    if file.filename == '':
        return None, jsonify({'error': 'No selected file'}), 400

    file_path = os.path.join(upload_dir, file.filename)
    file.save(file_path)
    return file_path, None, None


@app.route('/analyze', methods=['POST'])
def analyze_resume():
    resume_path, error, status_code = handle_file_upload(request.files, 'resume', app.config['UPLOAD_FOLDER'])
    if error:
        return error, status_code

    job_desc = request.form.get('job_description')
    if not job_desc:
        os.remove(resume_path)
        return jsonify({'error': 'Job description is required'}), 400

    try:
        # Extract text and keywords
        resume_text = functions.extract_text_from_pdf(resume_path)
        resume_keywords = functions.extract_keywords(resume_text)
        job_keywords = functions.extract_keywords(job_desc)

        # Calculate matches
        matched_keywords = list(set(resume_keywords) & set(job_keywords))
        missing_keywords = [kw for kw in job_keywords if kw not in resume_keywords]
        
        # Calculate percentages
        match_percent = round(len(matched_keywords) / len(job_keywords) * 100, 2) if job_keywords else 0
        coverage_percent = round(len(matched_keywords) / len(resume_keywords) * 100, 2) if resume_keywords else 0

        # Estimate experience (simple version)
        experience_years = functions.estimate_experience(resume_text)
        required_years = functions.estimate_required_experience(job_desc)

        # Generate response
        response = {
            'overallMatch': match_percent,
            'detailedAnalysis': {
                'skills': {
                    'matchPercentage': coverage_percent,
                    'matchingSkills': [kw.capitalize() for kw in matched_keywords[:15]],
                    'missingSkills': [kw.capitalize() for kw in missing_keywords[:15]],
                    'suggestedSkills': functions.suggest_related_skills(missing_keywords)[:10]
                },
                'experience': {
                    'yearsRequired': required_years,
                    'yearsActual': experience_years,
                    'meetsMinimum': experience_years >= required_years,
                    'meetsPreferred': experience_years >= (required_years + 2)
                },
                'ats': {
                    'score': functions.calculate_ats_score(resume_text),
                    'issues': functions.check_ats_issues(resume_text)
                }
            },
            'improvementSuggestions': functions.generate_suggestions(
                missing_keywords, 
                experience_years, 
                required_years,
                resume_text
            )
        }

        return jsonify(response)

    except Exception as e:
        print(f'Error occurred in /analyze: {e}')
        return jsonify({'error': 'An error occurred while processing the resume'}), 500
    finally:
        os.remove(resume_path)

@app.route('/recommend', methods=['POST'])
def recommend_jobs():
    resume_path, error, status_code = handle_file_upload(request.files, 'resume', app.config['UPLOAD_FOLDER'])
    if error:
        return error, status_code

    try:
        resume_text = functions.extract_text_from_pdf(resume_path)
        conn = functions.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, company, description FROM jobs")
        jobs = cursor.fetchall()
        cursor.close()
        conn.close()

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

        top_matches = sorted(recommendations, key=lambda x: x['matchPercentage'], reverse=True)[:5]
        return jsonify(top_matches)

    except Exception as e:
        print(f'Error occurred in /recommend: {e}')
        return jsonify({'error': 'An error occurred while recommending jobs'}), 500
    finally:
        os.remove(resume_path)


@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    file_path, error, status_code = handle_file_upload(request.files, 'file', tempfile.gettempdir())
    if error:
        return error, status_code

    try:
        text = ''
        if file_path.lower().endswith('.pdf'):
            with open(file_path, 'rb') as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ""
        else:
            return jsonify({'error': 'Unsupported file type'}), 400

        new_resume = Resume(name=os.path.basename(file_path), content=text)
        db.session.add(new_resume)
        db.session.commit()

        return jsonify({'message': 'Resume uploaded successfully', 'resume_id': new_resume.id}), 200

    except Exception as e:
        print(f'Error occurred in /upload_resume: {e}')
        db.session.rollback()
        return jsonify({'error': f'Error processing uploaded file: {str(e)}'}), 500
    finally:
        os.remove(file_path)


@app.route('/format-check', methods=['POST'])
def check_formatting():
    resume_path, error, status_code = handle_file_upload(request.files, 'resume', app.config['UPLOAD_FOLDER'])
    if error:
        return error, status_code

    try:
        resume_text = functions.extract_text_from_pdf(resume_path)
        suggestions = []
        strengths = []
        metrics = {
            'wordCount': len(resume_text.split()),
            'bulletPoints': resume_text.count('\n•') + resume_text.count('\n-'),
            'sections': 0,
            'hasContact': False,
            'hasSummary': False,
            'hasEducation': False,
            'hasExperience': False,
            'hasSkills': False
        }

        # ===== Conditional Checks =====
        # 1. Length Analysis (Only suggest if below threshold)
        if metrics['wordCount'] < 300:
            suggestions.append({
                'type': 'length',
                'message': "Resume appears too short ({} words). Ideal length is 300-500 words.".format(metrics['wordCount']),
                'priority': 'high' if metrics['wordCount'] < 200 else 'medium'
            })
        else:
            strengths.append("✓ Appropriate length ({} words)".format(metrics['wordCount']))

        # 2. Section Presence Checks
        required_sections = {
            'contact': (r'(email|phone|contact)', "Include contact information"),
            'summary': (r'(summary|objective|profile)', "Add a professional summary"),
            'education': (r'education', "Include education section"),
            'experience': (r'(experience|work\s?history)', "Add work experience"),
            'skills': (r'(skills|technical\s?skills)', "List technical skills")
        }

        for section, (pattern, suggestion) in required_sections.items():
            if not re.search(pattern, resume_text, re.IGNORECASE):
                suggestions.append({
                    'type': section,
                    'message': suggestion,
                    'priority': 'high' if section in ['contact', 'experience'] else 'medium'
                })
            else:
                strengths.append("✓ Complete {} section".format(section))
                metrics[f'has{section.capitalize()}'] = True

        # 3. Bullet Points Analysis (Only suggest if sparse)
        if metrics['bulletPoints'] < 10:
            suggestions.append({
                'type': 'formatting',
                'message': "Low bullet point count ({}). Use bullet points to highlight achievements.".format(metrics['bulletPoints']),
                'priority': 'medium'
            })
        else:
            strengths.append("✓ Good use of bullet points ({})".format(metrics['bulletPoints']))

        # 4. Contact Info Validation
        if not (re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', resume_text) and 
                re.search(r'(\+\d{1,2}\s?)?(\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}', resume_text)):
            suggestions.append({
                'type': 'contact',
                'message': "Missing email or phone number",
                'priority': 'high'
            })
        else:
            metrics['hasContact'] = True

        # 5. Skills Quantification (Only suggest if <5 skills)
        skills_match = re.search(r'(?i)skills:(.*?)(?:\n\n|\n\w+:)', resume_text)
        if skills_match:
            skills_count = len([s.strip() for s in skills_match.group(1).split(',') if s.strip()])
            metrics['skillsCount'] = skills_count
            if skills_count < 5:
                suggestions.append({
                    'type': 'skills',
                    'message': "Consider adding more skills (currently {})".format(skills_count),
                    'priority': 'medium'
                })
        elif metrics['hasSkills']:  # Has skills section but no countable skills
            suggestions.append({
                'type': 'skills',
                'message': "Skills section is empty",
                'priority': 'medium'
            })

        # 6. Section Count Analysis
        metrics['sections'] = sum(1 for section in required_sections if metrics[f'has{section.capitalize()}'])
        if metrics['sections'] >= 4:
            strengths.append("✓ Well-structured ({} sections)".format(metrics['sections']))
        else:
            suggestions.append({
                'type': 'structure',
                'message': "Resume could use more sections (currently {})".format(metrics['sections']),
                'priority': 'medium'
            })

        # ===== Final Filtering =====
        # Only include suggestions that meet minimum priority thresholds
        filtered_suggestions = [s for s in suggestions if s['priority'] in ('high', 'medium')]
        
        return jsonify({
            'suggestions': filtered_suggestions,
            'strengths': strengths,
            'metrics': metrics,
            'score': functions.calculate_score(filtered_suggestions)
        })

    except Exception as e:
        print(f"Error in /format-check: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        os.remove(resume_path)



@app.route('/api/analyze-match', methods=['POST'])
def analyze_match():
    resume_path, error, status_code = handle_file_upload(request.files, 'resume', app.config['UPLOAD_FOLDER'])
    if error:
        return error, status_code
    
    job_desc = request.form.get('job_description', '')
    try:
        resume_text = functions.extract_text_from_pdf(resume_path)
        match_percent, missing_kws = functions.calculate_match(resume_text, job_desc)
        suggested_skills = functions.suggest_related_skills(missing_kws)
        
        return jsonify({
            'matchPercentage': match_percent,
            'missingKeywords': missing_kws,
            'suggestedSkills': suggested_skills
        })
    finally:
        os.remove(resume_path)

@app.route('/api/extract-keywords', methods=['POST'])
def extract_keywords_endpoint():
    resume_path, error, status_code = handle_file_upload(request.files, 'resume', app.config['UPLOAD_FOLDER'])
    if error:
        return error, status_code
    
    try:
        resume_text = functions.extract_text_from_pdf(resume_path)
        keywords = functions.extract_keywords(resume_text)
        filtered_keywords = functions.filter_job_keywords(keywords)
        return jsonify({'keywords': filtered_keywords})
    finally:
        os.remove(resume_path)


@app.route('/api/extract-strengths', methods=['POST'])
def extract_strengths_endpoint():
    resume_path, error, status_code = handle_file_upload(request.files, 'resume', app.config['UPLOAD_FOLDER'])
    if error:
        return error, status_code
    
    try:
        resume_text = functions.extract_text_from_pdf(resume_path)
        strengths = functions.extract_strengths(resume_text)  # Use the new extract_strengths function
        return jsonify({'strengths': strengths})
    finally:
        os.remove(resume_path)


@app.route('/match', methods=['POST'])
def match_resume():
    data = request.json
    resume_id = data.get('resume_id')
    job_desc = data.get('job_description')

    if not resume_id or not job_desc:
        return jsonify({'error': 'resume_id and job_description are required'}), 400

    resume = Resume.query.get(resume_id)
    if not resume:
        return jsonify({'error': 'Resume not found'}), 404

    resume_text = f"Name: {resume.name}\nEmail: {resume.email}\nSkills: {resume.skills}\nExperience: {resume.experience}\nEducation: {resume.education}"

    ai_result = evaluate_resume_against_job(resume_text, job_desc)

    return jsonify({'match_result': ai_result})

if __name__ == '__main__':
    app.run(port=5001)