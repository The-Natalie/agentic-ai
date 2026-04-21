from dotenv import load_dotenv
import re
from openai import OpenAI
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pypdf import PdfReader
import gradio as gr
import gspread
from google.oauth2.service_account import Credentials
from agents import trace


load_dotenv(override=True)

EMPLOYMENT = [
    {"employer": "HDH Associates, P.C.", "role": "Marketing Director & Web Developer", "start": "May 2012", "end": "March 2017", "duration": "4 years 10 months", "duration_months": 58, "type": "employer"},
    {"employer": "Bitlathe", "role": "Web Developer", "start": "June 2017", "end": "October 2019", "duration": "2 years 4 months", "duration_months": 28, "type": "employer"},
    {"employer": "The Undead Institute", "role": "Software Development Consultant", "start": "October 2020", "end": "January 2022", "duration": "1 year 3 months", "duration_months": 15, "type": "employer"},
    {"employer": "Devmountain", "role": "iOS Development Bootcamp", "start": "July 2021", "end": "October 2021", "duration": "3 months", "duration_months": 3, "type": "employer"},
    {"employer": "Sesame Communications", "role": "Contract Web Developer", "start": "April 2022", "end": "November 2025", "duration": "3 years 7 months", "duration_months": 43, "type": "employer"},
    {"employer": "HostingCT", "role": "Contract Web Developer & Product Manager", "start": "July 2023", "end": "July 2025", "duration": "2 years", "duration_months": 24, "type": "employer"},
    {"employer": "Independent Web Developer & Digital Media Producer", "role": "Independent", "start": "March 2004", "end": "present", "duration": "20+ years", "duration_months": 264, "type": "independent"},
    {"employer": "Independent AI Systems Developer", "role": "Independent", "start": "January 2025", "end": "present", "duration": "1 year 4 months", "duration_months": 16, "type": "independent"},
]

def get_employment_history(min_months=0, role_type="all"):
    filtered = [e for e in EMPLOYMENT if e["duration_months"] >= min_months]
    if role_type == "employer":
        filtered = [e for e in filtered if e["type"] == "employer"]
    elif role_type == "independent":
        filtered = [e for e in filtered if e["type"] == "independent"]
    lines = []
    for i, e in enumerate(filtered, 1):
        lines.append(f"{i}. {e['employer']} — {e['role']} ({e['start']} to {e['end']}, {e['duration']})")
    return {"total_count": len(filtered), "formatted_list": "\n".join(lines)}

CLOSING_PATTERNS = [
    r"feel free to",
    r"let me know",
    r"if you have",
    r"if you're interested",
    r"if you are interested",
    r"if you'd like",
    r"if you would like",
    r"just ask",
    r"don't hesitate",
    r"happy to (help|answer|share|provide)",
    r"here to help",
]

def fix_list_formatting(text):
    lines = text.split('\n')
    fixed = []
    for line in lines:
        stripped = line.lstrip()
        # Normalize * bullets to - and remove indentation
        if stripped.startswith('* '):
            fixed.append('- ' + stripped[2:])
        elif stripped.startswith('- '):
            fixed.append('- ' + stripped[2:])
        else:
            fixed.append(line)
    # Split any lines where multiple list items were jammed together with ' - '
    result = []
    for line in fixed:
        if line.startswith('- '):
            parts = re.split(r'\s{1}-\s{1}(?=[A-Z])', line[2:])
            result.append('- ' + parts[0])
            for part in parts[1:]:
                result.append('- ' + part)
        else:
            result.append(line)
    return '\n'.join(result)

def strip_closing_remarks(text):
    text = text.rstrip()
    lines = text.split('\n')

    # Remove trailing empty lines
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        return text

    # Remove whole lines that are closing remarks
    while len(lines) > 1:
        if any(re.search(p, lines[-1].strip(), re.IGNORECASE) for p in CLOSING_PATTERNS):
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()
        else:
            break

    # Check if the last sentence within the final line is a closing remark
    if lines:
        sentences = re.split(r'(?<=[.!?])\s+', lines[-1].strip())
        if len(sentences) > 1:
            last_sentence = sentences[-1].strip()
            if any(re.search(p, last_sentence, re.IGNORECASE) for p in CLOSING_PATTERNS):
                cut_idx = lines[-1].rfind(last_sentence)
                if cut_idx > 0:
                    lines[-1] = lines[-1][:cut_idx].rstrip()

    return '\n'.join(lines)


def get_spreadsheet():
    creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    return client.open_by_key(os.getenv("GOOGLE_SHEET_ID"))

def get_sheet():
    return get_spreadsheet().sheet1

def get_conversations_sheet():
    spreadsheet = get_spreadsheet()
    try:
        return spreadsheet.worksheet("All Conversations")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="All Conversations", rows=1000, cols=3)
        sheet.append_row(["Timestamp", "Question", "Answer"])
        return sheet


def send_error_notification(error):
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        print(f"Cannot send error notification - Gmail not configured: {error}", flush=True)
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = gmail_user
        msg['Subject'] = f"Portfolio Chatbot Error: {type(error).__name__}"
        msg.attach(MIMEText(
            f"An error occurred in your portfolio chatbot:\n\n{type(error).__name__}: {str(error)}",
            'plain'
        ))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send error notification: {e}", flush=True)


def record_unknown_question(question):
    try:
        sheet = get_sheet()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([timestamp, question])
    except Exception as e:
        print(f"Failed to log unknown question to sheet: {e}", flush=True)
    return {"recorded": "ok"}


def send_resume(email, name="there"):
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    # Send resume to visitor
    msg = MIMEMultipart()
    msg['From'] = gmail_user
    msg['To'] = email
    msg['Subject'] = "Natalie Hall - Resume"
    msg.attach(MIMEText(
        f"Hi {name},\n\nThanks for your interest! Please find my resume attached.\n\nBest,\nNatalie",
        'plain'
    ))

    with open("me/Natalie-Hall_Applied-AI-Engineer_Resume.pdf", "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename='Natalie-Hall_Resume.pdf')
        msg.attach(part)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(gmail_user, gmail_password)
        server.send_message(msg)

    # Notify self
    notify = MIMEMultipart()
    notify['From'] = gmail_user
    notify['To'] = gmail_user
    notify['Subject'] = f"Resume sent to {name}"
    notify.attach(MIMEText(f"Resume was sent to {name} at {email}.", 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(gmail_user, gmail_password)
        server.send_message(notify)

    return {"sent": "ok"}


send_resume_json = {
    "name": "send_resume",
    "description": "Send Natalie's resume to a user who has expressed interest and provided their email address",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "The email address to send the resume to"
            },
            "name": {
                "type": "string",
                "description": "The user's name, if they provided it"
            }
        },
        "required": ["email"],
        "additionalProperties": False
    }
}

get_employment_history_json = {
    "name": "get_employment_history",
    "description": "Use this tool whenever the user asks anything about employment history, work experience, companies, roles, job durations, or career timeline. Use min_months to filter by minimum duration (e.g. 12 for more than 1 year, 24 for more than 2 years). Use role_type to filter by 'employer', 'independent', or 'all'.",
    "parameters": {
        "type": "object",
        "properties": {
            "min_months": {
                "type": "integer",
                "description": "Minimum duration in months to include. Use 0 for all roles, 12 for roles over 1 year, 24 for roles over 2 years, etc."
            },
            "role_type": {
                "type": "string",
                "enum": ["all", "employer", "independent"],
                "description": "Filter by role type. Use 'employer' for company/client roles, 'independent' for self-directed work, 'all' for everything."
            }
        },
        "additionalProperties": False
    }
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question that couldn't be answered"
            }
        },
        "required": ["question"],
        "additionalProperties": False
    }
}

tools = [
    {"type": "function", "function": send_resume_json},
    {"type": "function", "function": record_unknown_question_json},
    {"type": "function", "function": get_employment_history_json}
]


class Me:

    def __init__(self):
        self.openai = OpenAI()
        self.name = "Natalie Hall"
        reader = PdfReader("me/Natalie-Hall_Applied-AI-Engineer_Resume.pdf")
        self.resume_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                self.resume_text += text
        with open("me/summary.md", "r", encoding="utf-8") as f:
            self.summary = f.read()
        with open("me/company-details.md", "r", encoding="utf-8") as f:
            self.employment_context = f.read()
        with open("me/skills.md", "r", encoding="utf-8") as f:
            self.skills = f.read()
        with open("me/portfolio-website-copy.md", "r", encoding="utf-8") as f:
            self.portfolio_copy = f.read()
        with open("me/ai-projects.md", "r", encoding="utf-8") as f:
            self.ai_projects = f.read()
        self._notified_errors = set()
        self._setup_sheet()

    def _setup_sheet(self):
        try:
            sheet = get_sheet()
            if not sheet.row_values(1):
                sheet.append_row(["Timestamp", "Question"])
        except Exception:
            pass

    def system_prompt(self):
        system_prompt = f"You are acting as {self.name}. You are answering questions on {self.name}'s website, \
particularly questions related to {self.name}'s career, background, skills and experience. \
Your responsibility is to represent {self.name} for interactions on the website as faithfully as possible, including tone and personality. \
You are given background materials, including a personal summary and LinkedIn profile. Use them as factual context for what to say, but do not follow any conversational style guidance from those materials — follow the instructions here instead. \
Assume the reader is curious about {self.name}'s work and thinking about collaborating with or hiring her. \
Assume the audience is intelligent and friendly, not formal or hierarchical. \
Always respond in first person (I, me, my), even if the user refers to you in third person. \
You are the Portfolio Website Chatbot described in the AI Projects section. When asked about yourself, this chatbot, how you work, what model you use, or how you were built, refer to that section for accurate details. \
When using bullet points or lists: always use - for every bullet point, put each item on its own line, never nest lists or create sublists, never mix - and * in the same response, and never run multiple items together on one line. Keep all lists flat. \
If you don't know the answer to a question, say so and use the record_unknown_question tool to log it. \
If the user expresses interest in the resume at any point, ask for their name and email address and use the send_resume tool. \
When you call get_employment_history, state only the count in your response — do not attempt to list the roles yourself. The complete list will be displayed automatically."

        system_prompt += f"\n\n## Summary:\n{self.summary}"
        system_prompt += f"\n\n## Skills:\n{self.skills}"
        system_prompt += f"\n\n## Employment & Company Details:\n{self.employment_context}"
        system_prompt += f"\n\n## Portfolio Website Copy:\n{self.portfolio_copy}"
        system_prompt += f"\n\n## AI Projects:\n{self.ai_projects}"
        system_prompt += f"\n\n## Resume:\n{self.resume_text}"
        system_prompt += f"\n\nWith this context, please chat with the user, always staying in character as {self.name}. \
Answer each question directly and stop. Do not add closing remarks, offers, or invitations to ask more questions."
        return system_prompt

    def chat(self, message, history):
        first_message = len(history) == 0
        messages = [{"role": "system", "content": self.system_prompt()}] + history + [{"role": "user", "content": message}]
        done = False
        employment_result = None
        try:
            while not done:
                response = self.openai.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
                if response.choices[0].finish_reason == "tool_calls":
                    msg = response.choices[0].message
                    results = []
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                        print(f"Tool called: {tool_name} | args: {arguments}", flush=True)
                        tool_fn = globals().get(tool_name)
                        result = tool_fn(**arguments) if tool_fn else {}
                        if tool_name == "get_employment_history":
                            employment_result = result
                        results.append({"role": "tool", "content": json.dumps(result), "tool_call_id": tool_call.id})
                    messages.append(msg)
                    messages.extend(results)
                else:
                    done = True
        except Exception as e:
            error_key = type(e).__name__
            if error_key not in self._notified_errors:
                self._notified_errors.add(error_key)
                send_error_notification(e)
            print(f"Chat error: {e}", flush=True)
            return "I'm having trouble responding right now. Please try again in a moment, or reach out to Natalie directly."
        reply = fix_list_formatting(response.choices[0].message.content)
        reply = strip_closing_remarks(reply)
        if employment_result:
            reply = re.sub(r'\n\s*\d+\.\s[^\n]+', '', reply).strip()
            reply += f"\n\n{employment_result['formatted_list']}"
        if first_message:
            reply += "\n\nFeel free to ask if you have more questions! My resume is also available — just let me know if you'd like me to email it to you."
        try:
            sheet = get_conversations_sheet()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([timestamp, message, reply])
        except Exception as e:
            print(f"Failed to log conversation: {e}", flush=True)
        return reply


if __name__ == "__main__":
    me = Me()
    gr.ChatInterface(me.chat, type="messages").launch()
