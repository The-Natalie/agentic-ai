# AI Projects

## Portfolio Website Chatbot

### Overview
This chatbot is a deployed AI agent that lives on my portfolio website and answers questions as me — in my voice, with accurate information about my background, experience, and skills. Visitors can have a real conversation about my career, and the bot can email my resume on request. It started as a course exercise and evolved significantly through iteration and problem-solving.

### Tech Stack
- **Language:** Python
- **LLM:** OpenAI GPT-4o (via OpenAI API)
- **UI:** Gradio ChatInterface, deployed on Hugging Face Spaces
- **Email:** Gmail SMTP (smtplib) — sends resume to visitors, notifies me on requests
- **Logging:** Google Sheets API (gspread + google-auth) — two tabs: unknown questions and all conversations
- **PDF parsing:** pypdf — extracts text from resume PDF for LLM context
- **Environment:** python-dotenv, uv for dependency management

### How It Works
The bot is built around a system prompt that injects several context files — a personal summary, skills list, company details, portfolio website copy, and parsed resume text — so the LLM has rich, accurate context before any conversation starts.

Tool calls are the core of the agentic behavior. The bot has three tools:
- **`get_employment_history`** — returns structured employment data filtered by duration and role type (employer vs. independent). Used for any question about work history, companies, or job durations.
- **`send_resume`** — emails my resume PDF to the visitor and sends me a notification email.
- **`record_unknown_question`** — logs questions the bot couldn't answer to a Google Sheet with a timestamp.

Every conversation is also logged (question + answer + timestamp) to a separate Google Sheets tab for quality review.

### Key Features
- Answers questions in first person, in my voice and communication style
- Proactively offers to email my resume on the first message
- Accurately answers any question about employment history, job durations, or company counts — regardless of threshold (1 year, 2 years, etc.)
- Logs unanswered questions to Google Sheets for review
- Logs all conversations to Google Sheets for quality monitoring
- Closing remarks are controlled in code — offered once on the first message, never repeated

### How It Evolved
The project started as a lab from an Udemy Agentic AI course (originally built by Ed Donner). The base version used Pushover for push notifications and GPT-4o-mini.

**Changes I made:**
1. Replaced Pushover with Gmail SMTP — consolidated notifications and resume sending into one service
2. Added resume-sending capability — visitors can request my resume and receive it by email automatically
3. Replaced the LinkedIn PDF source with my resume PDF — cleaner parsing, more accurate and current data
4. Upgraded from GPT-4o-mini to GPT-4o — better factual reasoning
5. Added Google Sheets logging for unknown questions — avoids email bursts that could trigger Gmail's spam detection
6. Added full conversation logging — allows ongoing quality review
7. Added multiple context files — skills, company details, portfolio copy, in addition to the summary and resume
8. Refactored into a class-based structure (`Me` class) for cleaner organization

### Technical Challenges & Solutions

**Challenge: LLM giving inconsistent answers about employment history**
The LLM was missing roles, miscounting, and giving different answers to the same question. Even with the data in the system prompt, it would hallucinate or skip entries — particularly when roles overlapped in time (Sesame Communications and HostingCT ran simultaneously).

*Solution:* Built a `get_employment_history` tool that stores employment data as a structured Python list. The tool filters by minimum duration (in months) and role type, returning only relevant entries. The LLM calls the tool to get the data rather than trying to recall it from context.

**Challenge: LLM truncating the last item in numbered lists**
Even when the tool returned correct data, the LLM would consistently write the final list number (e.g. "5.") but leave it blank. This happened reliably regardless of list length.

*Solution:* Moved list generation entirely into code. After the tool is called, the chat method strips any numbered list the LLM generated using regex, then appends a pre-formatted list built from the tool result. The LLM provides only a prose intro sentence.

**Challenge: LLM adding closing remarks despite instructions**
The LLM consistently added phrases like "feel free to ask!" or "let me know if you need anything" at the end of every response, even when explicitly told not to.

*Solution:* Two-layer approach — a `strip_closing_remarks` function that uses regex to detect and remove common invitation patterns from the end of responses, plus a code-controlled first-message closing that appends a fixed string once and never again.

**Challenge: Inconsistent and broken list formatting**
The LLM generated lists inconsistently — mixing `*` and `-` bullet styles, nesting items as sublists with progressively smaller font sizes, and cramming multiple list items onto a single line separated by inline dashes. Formatting instructions in the system prompt had no effect.

A secondary bug compounded the issue: the `strip_closing_remarks` function split text on sentence boundaries and rejoined with `" "` (a space), which destroyed all newlines in the response. This collapsed properly formatted multi-line lists into a single line of prose, making it appear that lists had stopped working entirely.

*Solution:* Two fixes. First, a `fix_list_formatting` function that normalizes all `*` bullets to `-`, removes list item indentation, and splits inline ` - ` separated items onto their own lines using regex. Second, rewrote `strip_closing_remarks` to split on `\n` instead of sentence boundaries, preserving list structure — it now strips closing remarks by working backwards through lines, with a fallback to sentence-level stripping only within the final line.

**Challenge: First/third person inconsistency**
When users referred to me as "she" or "Natalie," the bot would sometimes respond in third person rather than staying in first person.

*Solution:* Added an explicit system prompt instruction: "Always respond in first person (I, me, my), even if the user refers to you in third person."

**Challenge: Google Credentials in .env**
Storing a multi-line service account JSON in a .env file caused python-dotenv parse errors and a JSON decode failure at runtime.

*Solution:* The entire JSON must be minified to a single line and wrapped in single quotes in the .env file. Generated using: `python3 -c "import json; print(json.dumps(json.load(open('credentials.json'))))"`.

### What I Learned
- LLMs are unreliable for factual recall and enumeration tasks — tools are the right solution for structured data
- Instruction-based control of LLM output has limits; code-level post-processing is more reliable for deterministic behavior
- System prompt length matters — context buried deep in a long prompt gets ignored; critical instructions belong at the end
- Separating concerns across multiple context files (summary, skills, company details) makes the system easier to maintain and update
- Google Sheets is a practical, free alternative to push notification services for low-volume logging
