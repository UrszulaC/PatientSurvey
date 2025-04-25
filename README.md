# Patient Survey Application

A comprehensive patient survey system with CRUD functionality for healthcare providers.

## Features

- Create, read, update, and delete surveys
- Predefined patient experience survey template
- Admin dashboard for survey management
- Patient interface for survey completion
- Response analysis and statistics

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/patient-survey-app.git
   cd patient-survey-app
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up MySQL database:
   ```bash
   mysql -u root -p -e "CREATE DATABASE patient_survey_db"
   ```

4. Configure database credentials in `app/config.py`

## Usage

Run the application:
```bash
python app/app.py
```

Run tests:
```bash
python -m unittest tests/test_survey_operations.py
```

## Predefined Survey Questions

1. Date of your visit?
2. Which site did you visit?
3. How easy was it to find the department today?
4. Were you informed when you will get your results?
5. What did we do well?
6. How can we improve?
7. How would you rate your experience?
