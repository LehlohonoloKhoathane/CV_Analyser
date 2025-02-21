import sqlite3
import pdfplumber
import re
import time
import streamlit as st
import pandas as pd
from docx import Document
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Function to extract skills from CV
def extract_skills_experience(file_path):
    text = ""
    if file_path.endswith(".pdf"):
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    elif file_path.endswith(".docx"):
        doc = Document(file_path)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    else:
        raise ValueError("Unsupported file format. Please upload a PDF or Word document.")

    skills = re.findall(r"(?:Skills|Technical Skills):?\s*(.*?)(?:\n\n|\n$|Experience|Education)", text, re.IGNORECASE | re.DOTALL)
    skills_list = skills[0].split(",") if skills else []
    return [skill.strip().lower() for skill in skills_list if skill.strip()]

# Function to extract skills from job descriptions
def extract_skills_from_jobs(jobs):
    job_skills = set()
    for job in jobs:
        description = job[3]  # Job description column
        found_skills = re.findall(r'\b[A-Za-z-]+\b', description)
        job_skills.update([skill.lower() for skill in found_skills])
    return job_skills

# Function to calculate job match percentage
def calculate_match_percentage(cv_skills, job_description):
    job_skills = set(re.findall(r'\b[A-Za-z-]+\b', job_description.lower()))
    matching_skills = set(cv_skills) & job_skills
    match_percentage = (len(matching_skills) / len(job_skills)) * 100 if job_skills else 0
    return round(match_percentage, 2), matching_skills

# Function to scrape jobs from Indeed
def scrape_jobs(skill, place):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("start-maximized")
    options.add_argument("disable-infobars")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    jobs = []
    try:
        url = f"https://za.indeed.com/jobs?q={skill}&l={place}"
        driver.get(url)
        time.sleep(5)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "job_seen_beacon"))
        )

        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        job_cards = soup.find_all('div', class_='job_seen_beacon')

        for job_card in job_cards:
            job_title_elem = job_card.find('h2', class_='jobTitle')
            job_title = job_title_elem.text.strip() if job_title_elem else 'No Job Title'

            company_elem = job_card.find('span', class_='companyName')
            company = company_elem.text.strip() if company_elem else 'No Company'

            salary_elem = job_card.find('div', class_='salary-snippet-container')
            salary = salary_elem.text.strip() if salary_elem else 'No Salary'

            description_elem = job_card.find('div', class_='job-snippet')
            description = description_elem.text.strip() if description_elem else 'No Description'

            job_link_elem = job_card.find('a', href=True)
            job_link = f"https://za.indeed.com{job_link_elem['href']}" if job_link_elem else 'No Link'

            jobs.append([job_title, company, salary, description, job_link])

    except Exception as e:
        st.error(f"Scraping Error: {e}")

    finally:
        driver.quit()

    return jobs

# Streamlit App
st.title("Job Matcher Based on CV")
uploaded_cv = st.file_uploader("Upload your CV (PDF or Word)", type=["pdf", "docx"])
location = st.text_input("Enter the job search location", placeholder="e.g., Johannesburg, Cape Town")

if st.button("Find Recommended Jobs"):
    if uploaded_cv and location:
        with open("uploaded_cv.pdf", "wb") as f:
            f.write(uploaded_cv.getbuffer())

        try:
            cv_skills = extract_skills_experience("uploaded_cv.pdf")
            if not cv_skills:
                st.warning("No skills detected in the CV. Consider adding a 'Skills' section.")
                st.stop()

            all_jobs = []
            for skill in cv_skills:
                all_jobs.extend(scrape_jobs(skill, location.strip()))

            if not all_jobs:
                st.warning(f"No jobs found for the skills in {location}.")
                st.stop()

            job_skills = extract_skills_from_jobs(all_jobs)
            missing_skills = job_skills - set(cv_skills)
            matching_skills = set(cv_skills) & job_skills

            st.success(f"Jobs found in {location} for your skills!")

            # Calculate match percentages
            job_matches = []
            for job in all_jobs:
                match_percentage, matched_skills = calculate_match_percentage(cv_skills, job[3])
                job_matches.append([*job, match_percentage, matched_skills])

            jobs_df = pd.DataFrame(job_matches, columns=["Job Title", "Company", "Salary", "Description", "Link", "Match %", "Matching Skills"])
            jobs_df["Link"] = jobs_df["Link"].apply(lambda x: f'<a href="{x}" target="_blank">Apply Here</a>' if x != 'No Link' else 'No Link')

            # Sort jobs by match percentage
            jobs_df = jobs_df.sort_values(by="Match %", ascending=False)

            # Display jobs with match percentage
            st.subheader("Recommended Jobs (Sorted by Match %)")
            st.write(jobs_df.to_html(escape=False, index=False), unsafe_allow_html=True)

            # Display skills analysis
            st.subheader("Skill Analysis")
            st.write(f"✅ Skills you have that match job requirements: {', '.join(matching_skills) if matching_skills else 'None'}")
            st.write(f"❌ Skills missing from your CV: {', '.join(missing_skills) if missing_skills else 'None'}")

        except ValueError as e:
            st.error(str(e))
            st.stop()

    else:
        st.error("Please upload a CV and enter a location.")
