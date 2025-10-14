⚔️ QuizIT: The Full-Stack MCQs Arena

🚀 Live Demo

Test your knowledge right now!
Prove your skills. Climb the global leaderboard.

👉 Launch [QuizIT](https://quizit-learnit-masterit.streamlit.app/) Live App 👈

✨ Project Overview
QuizIT is a full-stack, competitive quiz application built entirely using Python. It provides users with a dynamic range of Multiple-Choice Questions (MCQs) fetched in real-time and features a global leaderboard to track scores and foster competition.

This project demonstrates proficiency in cloud integration, external API handling, and scalable data persistence, making it a perfect tool for exam preparation and competitive self-assessment.

🛠️ Tech Stack & Key Features
Backend, Hosting & Data
Component

Technology

Purpose

Main Framework

Streamlit (Python)

Rapidly developing the UI and application logic without needing HTML/CSS/JS.

Database

Google Firebase Firestore

Real-time, serverless NoSQL database for secure, free, and persistent storage of user scores and ranking data.

External Data

Open Trivia Database (OpenTDB)

Fetches fresh, randomized MCQs based on user-selected categories and difficulty levels.

Hosting

Streamlit Community Cloud

Free, permanent deployment of the Python web application.

Core Features
Dynamic Quiz Generation: Users select from multiple categories (e.g., Geography, Science, Computers) and difficulty levels (Easy, Medium, Hard).

Global Leaderboard: Saves scores (including percentage correct, difficulty, and category) to Firestore and displays the top 10 ranked players.

Aesthetic Design: Custom CSS injection provides a clean, dark-mode UI with modern components and responsive layout.

Session Management: Uses Streamlit's st.session_state to track quiz progress and scores without cluttering the app.

👨‍💻 Installation & Local Setup
To run this project locally, ensure you have Python 3.9+ installed and follow these steps:

1. Clone the Repository
git clone [https://github.com/Pr1meGG/QuizIT.git](https://github.com/Pr1meGG/QuizIT.git)

2. cd QuizIT

3. Install Dependencies
pip install -r requirements.txt

4. Setup Firebase Secrets (Required for Leaderboard)
The application requires Firebase Admin SDK credentials for the leaderboard.

Create a Firebase Project and enable Firestore Database.

Generate a Service Account JSON key file.

Create a folder named .streamlit in your project root.

Inside .streamlit, create a file named secrets.toml.

Paste the contents of your JSON key into secrets.toml using the correct TOML format (as a dictionary).

4. Run the Application
streamlit run quiz_game.py

"`📜 Repository Structure
QuizIT/
│
├── quiz_game.py       <-- Main application file (UI, Logic, Firebase Calls)
└── requirements.txt   <-- Python dependencies list`"
