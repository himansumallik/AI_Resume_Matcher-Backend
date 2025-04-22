from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from models import db, Resume
import spacy
import os
import tempfile
from collections import Counter
import json


import re
import functions  # Import the functions module
import openai
from dotenv import load_dotenv
from gpt_model import evaluate_resume_against_job
from gpt_model import new_analyze_resume
from gpt_model import get_groq_resume_structure



from gpt_model import get_groq_response

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))  

app = Flask(__name__)
CORS(app)
nlp = spacy.load("en_core_web_sm")


#openai.api_key = "my_key"


# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", 'postgresql://postgres:7448596@localhost/resume_matcher')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()


resume_text = "Experienced Python developer with projects in web development and data science."
job_description = "Looking for a Python backend developer experienced in APIs and databases."

result = evaluate_resume_against_job(resume_text, job_description)


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
        if os.path.exists(resume_path):
            os.remove(resume_path)
        return jsonify({'error': 'Job description is required'}), 400

    try:
        # Extract text from resume
        resume_text = functions.extract_text_from_pdf(resume_path)

        # Structured AI Feedback via Groq
        print('Running structured AI analysis...')
        ai_result = new_analyze_resume(resume_text, job_desc)
        print('AI Analysis Complete')

        ai_analysis = ai_result.get('analysis')
        if not isinstance(ai_analysis, dict):
            print("AI analysis is not in expected dictionary format.")
            return jsonify({'error': 'Failed to parse structured AI response'}), 500

        response = {
            'overallMatch': ai_analysis.get('match_percent', 0),
            'detailedAnalysis': {
                'skills': {
                    'matchPercentage': ai_analysis.get('match_percent', 0),
                    'matchingSkills': [kw.capitalize() for kw in ai_analysis.get('matching_skills', [])[:15]],
                    'missingSkills': [kw.capitalize() for kw in ai_analysis.get('missing_skills', [])[:15]],
                    'suggestedSkills': ai_analysis.get('suggested_skills', [])[:10]
                },
                'experience': ai_analysis.get('experience', {}),
                'ats': ai_analysis.get('ats', {}),
                'aiAnalysis': ai_analysis.get('overallSummary', '')
            },
            'improvementSuggestions': ai_analysis.get('improvements', [])
        }

        return jsonify(response)

    except Exception as e:
        print(f'Error occurred in /analyze: {str(e)}')
        return jsonify({'error': 'An error occurred while processing the resume'}), 500
    finally:
        if os.path.exists(resume_path):
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
    try:
        resume_path, error, status_code = handle_file_upload(request.files, 'resume', app.config['UPLOAD_FOLDER'])
        if error:
            return error, status_code
        
        resume_text = functions.extract_text_from_pdf(resume_path)
        analysis = get_groq_resume_structure(resume_text)
        
        return jsonify({
            'suggestions': analysis['suggestions'],
            'strengths': analysis['strengths'],
            'metrics': analysis['metrics'],
            'score': functions.calculate_score(analysis['suggestions'])
        })
        
    except Exception as e:
        print(f"Endpoint error: {str(e)}")
        return jsonify({
            'error': 'Failed to analyze resume',
            'details': str(e)
        }), 500
        
    finally:
        if os.path.exists(resume_path):
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