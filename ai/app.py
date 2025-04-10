from flask import Flask, request, jsonify
import spacy
import PyPDF2
import os
import psycopg2
from flask_cors import CORS



app = Flask(__name__)
CORS(app)
nlp = spacy.load("en_core_web_sm")

# Ensure there's an upload folder to save files temporarily
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER






def get_db_connection():
    return psycopg2.connect(
        dbname='your_db_name',
        user='your_username',
        password='your_password',
        host='localhost',
        port='5432'
    )







def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text





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
    # Check if resume file is part of the request
    if 'resume' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    resume_file = request.files['resume']
    if resume_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Save the uploaded resume file temporarily
    resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_file.filename)
    resume_file.save(resume_path)

    if not os.path.exists(resume_path):
        return jsonify({'error': 'File not found after saving'}), 400

    job_desc = request.form.get('jobDescription')
    if not job_desc:
        return jsonify({'error': 'Job description is required'}), 400
    
    print("Received job description:", job_desc)  # Debugging line
    print("Received resume file:", resume_file.filename)  # Debugging line

    try:
        resume_text = extract_text_from_pdf(resume_path)
        match_percent, missing_keywords = calculate_match(resume_text, job_desc)
        return jsonify({
            'matchPercentage': match_percent,
            'missingKeywords': missing_keywords
        })
    except Exception as e:
        print('Error occurred:', e)  # Log the error to server console
        return jsonify({'error': 'An error occurred while processing the resume'}), 500






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




@app.route('/format-check', methods=['POST'])
def check_formatting():
    if 'resume' not in request.files:
        return jsonify({'error': 'No resume file uploaded'}), 400

    resume_file = request.files['resume']
    resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_file.filename)
    resume_file.save(resume_path)

    try:
        resume_text = extract_text_from_pdf(resume_path)
        
        sections = ['experience', 'education', 'skills', 'projects', 'summary']
        found_sections = [sec for sec in sections if sec in resume_text.lower()]
        missing_sections = [sec for sec in sections if sec not in found_sections]

        suggestions = []

        if 'contact' not in resume_text.lower():
            suggestions.append("Add your contact details at the top of the resume.")
        if len(resume_text.split()) < 200:
            suggestions.append("Your resume seems too short. Consider elaborating on your experiences.")
        if len(missing_sections) > 0:
            suggestions.append(f"Missing important sections: {', '.join(missing_sections).title()}")

        return jsonify({
            'foundSections': found_sections,
            'missingSections': missing_sections,
            'suggestions': suggestions
        })
    except Exception as e:
        print("Error in format-check:", e)
        return jsonify({'error': 'Something went wrong while checking resume formatting.'}), 500




if __name__ == '__main__':
    app.run(port=5001)
