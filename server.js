const express = require('express');
const cors = require('cors');
const multer = require('multer');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 5000;

app.use(cors());
app.use(express.json());

// Setup multer for file uploads
const storage = multer.diskStorage({
  destination: './uploads',
  filename: (req, file, cb) => {
    cb(null, Date.now() + path.extname(file.originalname));
  },
});
const upload = multer({ storage });
8
// Test API
app.get('/', (req, res) => {
  res.send('Resume Matcher Backend is running...');
});

// Route to handle resume upload and job description
app.post('/upload', upload.single('resume'), (req, res) => {
  const jobDescription = req.body.jobDescription;
  const resumePath = req.file.path;

  // For now, send dummy response (AI will be added later)
  res.json({
    message: 'Received resume and job description!',
    resumePath,
    jobDescription,
  });
});

app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
