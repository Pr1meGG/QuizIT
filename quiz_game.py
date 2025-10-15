import streamlit as st
import pandas as pd
import requests
import json
import base64
import html
import random
import time
import os

# --- GEMINI API / CONFIGURATION ---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
# FIX: Use a stable getter with a default path, ensuring the key is available.
# We retrieve the key from the [gemini] section of st.secrets.
API_KEY = st.secrets.get("gemini", {}).get("api_key", "")

# --- FIREBASE / LEADERBOARD SETUP ---
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    
    # Check if a Firestore service account is available in st.secrets
    if 'firestore_creds' in st.secrets:
        if not firebase_admin._apps:
            # FIX: Convert Streamlit AttrDict to standard dict for Firebase compatibility
            creds_dict = st.secrets['firestore_creds']
            cred = credentials.Certificate(dict(creds_dict))
            firebase_admin.initialize_app(cred)
            st.session_state.db = firestore.client()
        elif 'db' not in st.session_state:
            st.session_state.db = firestore.client()
    else:
        st.session_state.db = None
except ImportError:
    st.session_state.db = None
    if 'firebase_admin_installed' not in st.session_state:
        st.warning("⚠️ Leaderboard Offline: Python library 'firebase-admin' not found.")
        st.session_state.firebase_admin_installed = False


# --- 1. CONFIGURATION AND API SETUP (OpenTDB) ---
API_URL = "https://opentdb.com/api.php"

DIFFICULTY_OPTIONS = {
    "Very Easy (All)": "all",
    "Easy": "easy",
    "Medium": "medium",
    "Hard": "hard",
}

CATEGORY_OPTIONS = {
    "Mix (Any Category)": 0,
    "General Knowledge": 9,
    "Books": 10,
    "Film": 11,
    "Music": 12,
    "Science & Nature": 17,
    "Computers": 18,
    "Mathematics": 19,
    "Geography": 22,
    "History": 23,
    "Sports": 21,
}

# --- Function to fetch explanation using Gemini ---
def fetch_explanation(question, correct_answer):
    """Fetches a detailed, grounded explanation for a question/answer pair using the Gemini API."""
    
    # Check the key here again to prevent the 403 error message
    if not API_KEY:
        return "Explanation API Key is missing. Cannot retrieve detailed rationale."

    prompt = f"Provide a brief, single-paragraph, factual explanation detailing why '{correct_answer}' is the correct answer for the question: '{question}'."
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {} }],
        "systemInstruction": {
            "parts": [{"text": "You are a world-class trivia expert. Provide clear, concise, and educational explanations based on real-time search results."}]
        }
    }
    
    try:
        # Using a direct requests call as this is running server-side
        response = requests.post(
            f"{GEMINI_API_URL}?key={API_KEY}",
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        
        result = response.json()
        
        # Check for specific error message in the response body (e.g., rate limiting)
        if 'error' in result:
             return f"Error retrieving explanation: {result['error'].get('message', 'Unknown API Error')}"

        text = result['candidates'][0]['content']['parts'][0]['text']
        return text.strip()
        
    except requests.exceptions.HTTPError as e:
        # Handle the 403 error explicitly
        return f"Error retrieving explanation: HTTP {e.response.status_code}. The API key might be restricted."
    except Exception as e:
        return f"Could not retrieve a detailed explanation: {e}"


def fetch_questions(difficulty, category_id, amount=10):
    """Fetches questions from the OpenTDB API based on user settings."""
    with st.spinner(f"Fetching {amount} questions... 🚀"):
        params = {
            "amount": amount,
            "category": category_id,
            "difficulty": difficulty if difficulty != "all" else "",
            "type": "multiple",
            "encode": "base64"
        }
        
        try:
            response = requests.get(API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data['response_code'] == 0:
                return data['results']
            else:
                st.error("API Error: Could not fetch questions. Try 'Mix' category or 'Very Easy' difficulty.")
                return None
        except requests.exceptions.RequestException as e:
            st.error(f"Network Error: Could not connect to the trivia service. ({e})")
            return None

def process_question_data(results):
    """Decodes Base64 data and structures questions into a clean DataFrame."""
    processed_data = []
    if not results:
        return pd.DataFrame()

    for item in results:
        try:
            question = html.unescape(base64.b64decode(item['question']).decode('utf-8'))
            correct_answer = html.unescape(base64.b64decode(item['correct_answer']).decode('utf-8'))
            incorrect_answers = [html.unescape(base64.b64decode(ans).decode('utf-8')) for ans in item['incorrect_answers']]
            
            all_options = incorrect_answers + [correct_answer]
            random.shuffle(all_options)

            processed_data.append({
                "question": question,
                "options": all_options,
                "answer": correct_answer,
                "difficulty": html.unescape(base64.b64decode(item['difficulty']).decode('utf-8')),
                "category": html.unescape(base64.b64decode(item['category']).decode('utf-8'))
            })
        except Exception as e:
            continue

    return pd.DataFrame(processed_data)

# --- 2. Streamlit App Logic ---

def check_answer():
    """
    Checks the user's selected answer from the form, updates score, and moves the index.
    """
    if f'radio_{st.session_state.current_index}' not in st.session_state:
        return

    user_choice = st.session_state[f'radio_{st.session_state.current_index}']
    correct_answer = st.session_state.questions_df.iloc[st.session_state.current_index]['answer']
    question = st.session_state.questions_df.iloc[st.session_state.current_index]['question'] # Get question for explanation fetch
    
    # Initialize or append to history
    if 'answer_history' not in st.session_state:
        st.session_state.answer_history = []
    
    is_correct = user_choice == correct_answer
    
    st.session_state.submitted = True
    
    # Store the result for review
    st.session_state.answer_history.append({
        'question': question,
        'user_answer': user_choice,
        'correct_answer': correct_answer,
        'is_correct': is_correct,
        'explanation': None # Will be fetched when review mode is toggled
    })

    if is_correct:
        st.session_state.score += 1
        st.session_state.last_result = "✅ Correct! Moving to the next question."
    else:
        st.session_state.last_result = f"❌ Incorrect. The correct answer was: **{correct_answer}**. Moving on."

    st.session_state.current_index += 1

def start_quiz():
    """Fetches questions and starts the quiz based on selected options."""
    category_id = st.session_state['selected_category']
    difficulty = st.session_state['selected_difficulty']
    
    results = fetch_questions(difficulty, category_id)
    
    if results:
        questions_df = process_question_data(results)
        if not questions_df.empty:
            st.session_state.questions_df = questions_df
            st.session_state.num_questions = len(questions_df)
            st.session_state.score = 0
            st.session_state.current_index = 0
            st.session_state.submitted = False
            st.session_state.quiz_started = True
            st.session_state.score_submitted = False
            st.session_state.last_result = None
            st.session_state.review_mode = False # Disable review mode
            st.session_state.answer_history = [] # Clear history
            st.rerun()
        else:
            st.error("Fetched questions were empty or corrupted. Please try again.")
    else:
        pass 

def start_quiz_same_settings():
    """Starts a new quiz using the last used settings."""
    st.session_state.quiz_started = False 
    start_quiz() 


def reset_quiz():
    """Resets the entire quiz session back to the settings screen."""
    if 'quiz_started' in st.session_state:
        del st.session_state['quiz_started']
    
    st.session_state.current_index = 0
    st.session_state.score = 0
    st.session_state.submitted = False
    st.session_state.score_submitted = False
    st.session_state.last_result = None
    st.session_state.review_mode = False
    if 'questions_df' in st.session_state:
        del st.session_state['questions_df']
    if 'num_questions' in st.session_state:
        del st.session_state['num_questions']
    if 'answer_history' in st.session_state:
        del st.session_state['answer_history']
    
    st.rerun()

def toggle_review_mode():
    """Toggles the state to view the quiz review page and fetches explanations if needed."""
    if not st.session_state.get('review_mode', False):
        # Only fetch explanations when entering review mode
        if st.session_state.get('answer_history'):
            if not API_KEY:
                st.warning("Cannot fetch explanations: Gemini API Key is missing from the environment.")
                st.session_state.review_mode = not st.session_state.get('review_mode', False)
                st.rerun()
                return

            # Use a progress bar to show fetching status
            progress_bar = st.progress(0, text="Fetching detailed explanations... Please wait.")
            
            history_length = len(st.session_state.answer_history)
            
            for i, item in enumerate(st.session_state.answer_history):
                if item.get('explanation') is None:
                    # Fetch and store the explanation
                    explanation = fetch_explanation(item['question'], item['correct_answer'])
                    st.session_state.answer_history[i]['explanation'] = explanation
                
                # Update progress bar
                progress_bar.progress((i + 1) / history_length)
                
            progress_bar.empty() # Clear the progress bar after completion

        
    st.session_state.review_mode = not st.session_state.get('review_mode', False)
    st.rerun()

# --- 3. FIRESTORE LEADERBOARD FUNCTIONS ---

def save_score_to_db(username, score, num_questions, difficulty, category):
    """Saves the user's quiz score to Firestore."""
    db = st.session_state.get('db')
    if db is None:
        st.error("Cannot save score: Firestore is not initialized or credentials are missing.")
        return

    collection_ref = db.collection(u'quiz_scores')
    percentage = (score / num_questions) * 100 if num_questions > 0 else 0
    
    score_data = {
        'username': username,
        'score': score,
        'total_questions': num_questions,
        'percentage': percentage,
        'difficulty': difficulty,
        'category': category,
        'timestamp': firestore.SERVER_TIMESTAMP
    }
    
    try:
        collection_ref.add(score_data)
        st.success(f"Score saved! Good job, {username}! Check the Leaderboard.")
    except Exception as e:
        st.error(f"Error saving score to Firestore: {e}")

def get_leaderboard_data(limit=10):
    """Fetches the top scores from Firestore."""
    db = st.session_state.get('db')
    if db is None:
        # Placeholder data for when DB is offline
        return pd.DataFrame({
            'User': ['Pr1meGG'], 'Score': ['Leaderboard Offline'], 'Difficulty': ['N/A'], 'Category': ['N/A']
        })

    collection_ref = db.collection(u'quiz_scores')
    
    try:
        query = collection_ref.order_by(u'percentage', direction=firestore.Query.DESCENDING).limit(limit)
        results = query.stream()
        
        leaderboard = []
        for doc in results:
            data = doc.to_dict()
            leaderboard.append({
                'User': data.get('username', 'Anonymous'),
                'Score': f"{data.get('score', 0)} / {data.get('total_questions', 0)} ({data.get('percentage', 0):.1f}%)",
                'Difficulty': data.get('difficulty', 'N/A'),
                'Category': data.get('category', 'N/A')
            })
        
        return pd.DataFrame(leaderboard)
        
    except Exception as e:
        st.info("No scores found yet! Be the first one to set a record.")
        return pd.DataFrame()

def display_leaderboard():
    """Fetches and displays the top scores from Firestore."""
    st.subheader("🏆 Global Leaderboard")
    
    if st.session_state.get('db') is None:
        st.markdown(
            """
            _**Leaderboard Offline:** Cannot connect to Firestore. Check your `.streamlit/secrets.toml` file._
            """
        )
        df_placeholder = get_leaderboard_data(limit=0)
        st.table(df_placeholder)
        return
    
    with st.spinner('Loading top scores...'):
        df_leaderboard = get_leaderboard_data(limit=10)
    
    if not df_leaderboard.empty:
        st.dataframe(df_leaderboard, hide_index=True, use_container_width=True)
    else:
        st.info("No scores found yet! Be the first one to set a record.")

def display_review_page():
    """Displays the answers and feedback for the completed quiz."""
    st.header("🔍 Quiz Review")
    st.markdown("---")
    
    if not st.session_state.get('answer_history'):
        st.warning("No quiz history found to review.")
        st.button("Return to Results", on_click=toggle_review_mode)
        return
        
    for i, item in enumerate(st.session_state.answer_history):
        is_correct = item['is_correct']
        icon = "✅" if is_correct else "❌"
        
        # Use HTML for better styling in the review page
        # FIX: The crucial change is ensuring this st.markdown call has unsafe_allow_html=True
        st.markdown(f"""
            <div style="padding: 15px; margin-bottom: 20px; border: 1px solid {'#1f3b4d' if is_correct else '#a83c3c'}; border-left: 5px solid {'#52c2c2' if is_correct else '#e84c4c'}; border-radius: 8px;">
                <p style="font-weight: bold; font-size: 1.1em; color: #fff;">{icon} Question {i+1}: {item['question']}</p>
                <p style="margin-bottom: 5px;">**Your Answer:** <span style="color: {'#52c2c2' if is_correct else '#e84c4c'}; font-weight: bold;">{item['user_answer']}</span> ({'Perfect!' if is_correct else 'Incorrect'})</p>
                <p style="margin-top: 0;">**Correct Answer:** <span style="color: #52c2c2; font-weight: bold;">{item['correct_answer']}</span></p>
                
                <div style="margin-top: 15px; padding-top: 10px; border-top: 1px dashed #333;">
                    <p style="font-weight: bold; color: #fff;">💡 Why it's right:</p>
                    <p style="color: #ccc;">{item.get('explanation', 'Fetching explanation...')}</p>
                </div>
            </div>
            """, unsafe_allow_html=True) # <-- THIS IS THE MISSING KEY

    st.markdown("---")
    st.button("Return to Results", on_click=toggle_review_mode, type="secondary")


# --- 4. The Main App Function ---

def main():
    """The main Streamlit application function."""
    # FIX: Adding safe defaults to st.session_state before reading them
    if 'selected_difficulty' not in st.session_state:
        st.session_state['selected_difficulty'] = list(DIFFICULTY_OPTIONS.values())[0]
    if 'selected_category' not in st.session_state:
        st.session_state['selected_category'] = list(CATEGORY_OPTIONS.values())[0]
    if 'review_mode' not in st.session_state:
        st.session_state.review_mode = False

    st.set_page_config(page_title="The Python Quiz Master", layout="centered", initial_sidebar_state="expanded")
    
    st.markdown("""
        <style>
            /* Custom CSS for a clean, dark, modern look */
            .css-1d3c0cr { padding-top: 2rem; }
            .stButton>button { 
                border-radius: 12px; 
                transition: all 0.3s;
            }
            .stButton>button:hover {
                transform: scale(1.02);
            }
            .stAlert { border-radius: 12px; }
            
            /* FIX: Hide the yellow 'Calling st.rerun() within a callback is a no-op.' banner */
            /* This targets the specific element responsible for the annoying warning */
            div[data-testid="stStatusWidget"] {
                display: none !important;
                height: 0px !important;
                visibility: hidden !important;
            }
            
            /* Hiding Streamlit's default hamburger menu and footer/header */
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .css-1kyxreq { visibility: hidden; } /* Hides the sidebar button container */
            
            /* Custom aesthetic for the dynamic welcome section */
            .welcome-box {
                background-color: #1f3b4d;
                padding: 25px;
                border-radius: 15px;
                margin-top: 20px;
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.4);
                color: #e6f7ff;
            }
            .welcome-box h3 {
                color: #52c2c2;
                margin-top: 0;
            }
        </style>
        """, unsafe_allow_html=True)
    
    st.title("🧠 The Python Quiz Master")
    st.markdown("---")

    if 'score_submitted' not in st.session_state:
        st.session_state.score_submitted = False
    if 'last_result' not in st.session_state:
        st.session_state.last_result = None
        
    selected_difficulty_name = next(
        (k for k, v in DIFFICULTY_OPTIONS.items() if v == st.session_state.get('selected_difficulty')), 
        list(DIFFICULTY_OPTIONS.keys())[0]
    )
    selected_category_name = next(
        (k for k, v in CATEGORY_OPTIONS.items() if v == st.session_state.get('selected_category')), 
        list(CATEGORY_OPTIONS.keys())[0]
    )

    # --- Sidebar control and visibility ---
    with st.sidebar:
        st.header("App Control")
        st.button("Reset App", on_click=reset_quiz, use_container_width=True, help="Reset the app to the main settings page.")
        st.info("App configuration is on the main dashboard for a cleaner look.")


    # --- Quiz Workflow ---
    if st.session_state.get('review_mode', False):
        display_review_page()
        
    elif 'quiz_started' not in st.session_state or st.session_state.quiz_started is False:
        # --- Landing Page (UX UPGRADE) ---
        st.header("Welcome to the Ultimate MCQs Challenge!")
        
        # 1. Selection Inputs (Moved from Sidebar)
        col1, col2 = st.columns(2)
        with col1:
            selected_difficulty = st.selectbox(
                "Select Difficulty:",
                list(DIFFICULTY_OPTIONS.keys()),
                index=list(DIFFICULTY_OPTIONS.keys()).index(selected_difficulty_name),
                key='difficulty_select'
            )
            st.session_state['selected_difficulty'] = DIFFICULTY_OPTIONS[selected_difficulty]

        with col2:
            selected_category = st.selectbox(
                "Select Topic/Subject:",
                list(CATEGORY_OPTIONS.keys()),
                index=list(CATEGORY_OPTIONS.keys()).index(selected_category_name),
                key='category_select'
            )
            st.session_state['selected_category'] = CATEGORY_OPTIONS[selected_category]

        st.markdown("---")
        
        # 2. Start Button
        st.button("🚀 START NEW QUIZ", on_click=start_quiz, type="primary", use_container_width=True)
        
        st.markdown("---")

        # 3. Welcome Box (Aesthetics)
        st.subheader("Challenge Details:")
        st.markdown(
            f"""
            <div class="welcome-box">
                <h3>Ready to prove your genius?</h3>
                <p>🌎 Challenge yourself with fresh, real-time questions in **{selected_category_name}**.</p>
                <p>💪 Set your skill level to **{selected_difficulty_name}**.</p>
                <p>🥇 Rank on the Global Leaderboard!</p>
                <p>Click the **'START NEW QUIZ'** button above to begin your challenge!</p>
            </div>
            """, unsafe_allow_html=True
        )
        
        st.markdown("---")
        
        display_leaderboard()
        

    elif st.session_state.current_index < st.session_state.num_questions:
        # --- Active Quiz Screen ---
        num_questions = st.session_state.num_questions
        current_index = st.session_state.current_index
        score = st.session_state.score
        questions_df = st.session_state.questions_df
        
        # Display previous result if available
        if st.session_state.last_result:
            if st.session_state.last_result == "✅ Correct! Moving to the next question.":
                st.success(st.session_state.last_result)
            else:
                st.error(st.session_state.last_result)
            st.session_state.last_result = None # Clear feedback after display

        st.markdown(f"**Topic:** `{selected_category_name}` | **Difficulty:** `{selected_difficulty_name}`")
        
        st.markdown(f"**Question {current_index + 1} of {num_questions}**")
        st.progress((current_index + 1) / num_questions)
        st.markdown("---")


        current_q = questions_df.iloc[current_index]
        
        question_text = current_q['question']
        options = current_q['options']
        
        st.subheader(f"❓ {question_text}")
        
        # FIX: Using st.form's onSubmit to prevent double-click issues and calling st.rerun
        with st.form(key=f'question_form_{current_index}', clear_on_submit=False):
            user_choice = st.radio(
                "Select your answer:",
                options,
                index=None,
                key=f'radio_{current_index}'
            )
            
            # Submit button calls check_answer, which updates the state and calls rerun
            submit_button = st.form_submit_button(
                label='Submit Answer', 
                type="secondary",
                on_click=check_answer # Direct state update and implicitly triggers rerun
            )


    else:
        # --- Quiz Finished Screen (UX UPGRADE) ---
        st.balloons()
        st.header("🎉 Quiz Completed! Time to Check Your Rank.")
        final_score = st.session_state.score
        num_questions = st.session_state.num_questions
        
        percentage = (final_score / num_questions) * 100 if num_questions > 0 else 0

        st.metric(label="Final Score", value=f"{final_score} / {num_questions}", delta_color="off")
        st.metric(label="Percentage Correct", value=f"{percentage:.1f}%")
        
        st.markdown(f"**Topic:** `{selected_category_name}` | **Difficulty:** `{selected_difficulty_name}`")
        st.markdown("---")

        # --- Score Saving Section ---
        if st.session_state.score_submitted is False and st.session_state.get('db') is not None:
            difficulty_name = selected_difficulty_name
            category_name = selected_category_name
            
            with st.form("score_submission_form"):
                st.subheader("Submit Your Score to the Leaderboard")
                username = st.text_input("Enter your unique username (e.g., Pr1meGG):", max_chars=15)
                
                submit_score_btn = st.form_submit_button("Submit Score", type="primary")

                if submit_score_btn:
                    if username:
                        save_score_to_db(
                            username, 
                            final_score, 
                            num_questions, 
                            difficulty_name, 
                            category_name
                        )
                        st.session_state.score_submitted = True
                        st.rerun()
                    else:
                        st.warning("Please enter a username to submit your score.")

        
        # --- Leaderboard Display ---
        display_leaderboard()
        
        st.markdown("---")
        
        # UX UPGRADE: Custom button row for post-quiz options
        st.subheader("What's Next?")
        col_end1, col_end2, col_end3, col_end4 = st.columns(4) # Added one column for Review
        
        with col_end1:
            st.button("Start New Challenge", on_click=start_quiz_same_settings, help="Uses the current settings: same Topic and Difficulty.", type="primary", use_container_width=True)
            
        with col_end2:
            st.button("Change Settings", on_click=reset_quiz, help="Go back to the main menu to change Topic or Difficulty.", type="secondary", use_container_width=True)

        with col_end3:
            # New Feature: Review Answers
            st.button("Review Answers", on_click=toggle_review_mode, help="Check your answers and the correct solutions.", type="secondary", use_container_width=True)

        with col_end4:
             # This button simply forces a refresh of the leaderboard data
            st.button("Refresh Leaderboard", on_click=lambda: st.rerun(), help="Refresh to see latest scores.", type="secondary", use_container_width=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error("An error occurred during application startup. Please check the console.")
        st.code(f"Error: {e}")
