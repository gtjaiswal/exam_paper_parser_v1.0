# 🧠 Exam Paper Parser v1.0

AI-driven project to **read, understand, and structure exam papers** automatically.  
This repository is the foundation for a future Exam Paper Builder system that can generate practice papers and question banks using past exam data.

---

## 🚀 Features (Phase 1)

- Extracts text, tables, and images from exam PDFs (`PyMuPDF`, `pdfplumber`)
- Cleans and structures questions, sub-questions, and marks
- Stores structured outputs in CSV/JSON format
- Modular code in `/src` and exploratory notebooks in `/notebooks`

---

## 📁 Project Structure

exam_paper_parser_v1.0/
├─ data/
│ ├─ raw_papers/ # Original exam PDFs (not committed)
│ 
│
├─ notebooks/
│ ├─ 
│
├─ src/
│
├─ .gitignore
└─ README.md

---

## ⚙️ Environment Setup

**Requires:** [Miniconda](https://docs.conda.io/en/latest/miniconda.html)


# 1. Create environment
conda create -n exam_parser python=3.11
conda activate exam_parser

# 2. Install packages
conda install -c conda-forge jupyterlab pandas pdfplumber matplotlib spacy
pip install pymupdf

# Launch JupyterLab
jupyter lab

import fitz
doc = fitz.open("../data/raw_papers/sample.pdf")
print(doc[0].get_text("text")[:500])

🧠 Next Phases
Phase	Focus	Key Outcome
1	PDF Parsing & Structuring	Clean dataset of questions
2	Question Understanding	Classify and tag questions
3	AI Generation	Generate new or predicted exam papers
👩‍💻 Author

Garima Jaiswal
Learning Path: Python → Document Understanding → AI Project Development
🌐 GitHub: @gtjaiswal
