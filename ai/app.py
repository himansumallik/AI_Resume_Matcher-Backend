from flask import Flask, request, jsonify
import spacy
import PyPDF2
import os

app = Flask(__name__)
nlp = spacy.load("en_core_web_sm")

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
    resume_path = request.json.get('resumePath')
    job_desc = request.json.get('jobDescription')

    if not os.path.exists(resume_path):
        return jsonify({'error': 'Resume file not found'}), 400

    resume_text = extract_text_from_pdf(resume_path)
    match_percent, missing_keywords = calculate_match(resume_text, job_desc)

    return jsonify({
        'matchPercentage': match_percent,
        'missingKeywords': missing_keywords
    })

if __name__ == '__main__':
    app.run(port=5001)
