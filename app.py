from flask import Flask, request, render_template, Response, jsonify
import re
import requests
from bs4 import BeautifulSoup
import sqlite3
import pandas as pd
import time

# Optional: Selenium for JavaScript-based websites
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

# 🔹 Initialize SQLite Database
def init_db():
    with sqlite3.connect("emails.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                emails TEXT
            )
        """)
        conn.commit()

# 🔹 Save Extraction History
def save_history(url, emails):
    with sqlite3.connect("emails.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO email_history (url, emails) VALUES (?, ?)", (url, ",".join(emails)))
        conn.commit()

# 🔹 Validate URL (Ensure it starts with http or https)
def validate_url(url):
    if not url.startswith("http"):
        return "https://" + url
    return url

# 🔹 Extract Emails from Static Websites (Using BeautifulSoup)
def extract_emails(url, depth=1, domain=None):
    try:
        url = validate_url(url)
        visited_urls = set()
        emails = set()
        urls_to_visit = [url]

        for _ in range(depth):
            new_urls = []
            for url in urls_to_visit:
                if url in visited_urls:
                    continue
                
                response = requests.get(url, timeout=5)
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text()
                
                # Extract emails and filter by domain (if specified)
                found_emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
                if domain:
                    found_emails = {email for email in found_emails if email.endswith(domain)}

                emails.update(found_emails)

                # Extract additional links
                for link in soup.find_all("a", href=True):
                    absolute_link = requests.compat.urljoin(url, link["href"])
                    if absolute_link.startswith("http"):
                        new_urls.append(absolute_link)

                visited_urls.add(url)

            urls_to_visit = new_urls

        return emails
    except Exception as e:
        return set([str(e)])

# 🔹 Extract Emails from JavaScript Websites (Using Selenium)
def extract_emails_selenium(url):
    url = validate_url(url)
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get(url)
        time.sleep(3)
        text = driver.page_source
        emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
        return emails
    finally:
        driver.quit()

# 🔹 Main Route (UI)
@app.route("/", methods=["GET", "POST"])
def index():
    emails = []
    method_used = "BeautifulSoup"

    if request.method == "POST":
        url = request.form.get("url")
        domain = request.form.get("domain")
        use_selenium = request.form.get("use_selenium")

        if url:
            if use_selenium:
                emails = extract_emails_selenium(url)
                method_used = "Selenium"
            else:
                emails = extract_emails(url, domain=domain)

            save_history(url, emails)

    return render_template("index.html", emails=emails, method_used=method_used)

# 🔹 Download Extracted Emails
@app.route("/download", methods=["POST"])
def download():
    emails = request.form.getlist("emails")
    file_format = request.form.get("format", "csv")

    if file_format == "csv":
        output = "\n".join(emails)
        response = Response(output, mimetype="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=emails.csv"
    elif file_format == "txt":
        output = "\n".join(emails)
        response = Response(output, mimetype="text/plain")
        response.headers["Content-Disposition"] = "attachment; filename=emails.txt"
    elif file_format == "excel":
        df = pd.DataFrame(emails, columns=["Email"])
        output = df.to_csv(index=False)
        response = Response(output, mimetype="application/vnd.ms-excel")
        response.headers["Content-Disposition"] = "attachment; filename=emails.xlsx"

    return response

# 🔹 View Extraction History
@app.route("/history", methods=["GET"])
def history():
    with sqlite3.connect("emails.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM email_history ORDER BY id DESC LIMIT 50")  # Show latest 50
        records = cursor.fetchall()
    return render_template("history.html", records=records)

# 🔹 API Endpoint for Email Extraction
@app.route("/api/extract", methods=["GET"])
def api_extract():
    url = request.args.get("url")
    use_selenium = request.args.get("selenium", "false").lower() == "true"

    if not url:
        return jsonify({"error": "Missing URL"}), 400

    emails = extract_emails_selenium(url) if use_selenium else extract_emails(url)
    return jsonify({"emails": list(emails)})

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
