import streamlit as st
import pandas as pd
import requests
import json
import base64
import html
import random
import time

# --- FIREBASE / LEADERBOARD SETUP ---
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    
    # Check if a Firestore service account is available in st.secrets
    if 'firestore_creds' in st.secrets:
        if not firebase_admin._apps:
            # st.secrets returns an AttrDict (a dictionary-like object)
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


# --- 1. CONFIGURATION AND API SETUP ---
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

def check_answer(user_choice, correct_answer):
    """Checks the user's selected answer."""
    if st.session_state.submitted:
        return

    st.session_state.submitted = True

    if user_choice == correct_answer:
        st.session_state.score += 1
        st.success("✅ Correct! You nailed it, genius!")
    else:
        st.error(f"❌ Incorrect. The correct answer was: **{correct_answer}**")
        st.info("No worries, keep pushing!")
    
    st.button("Next Question", on_click=next_question, type="primary")

def next_question():
    """Moves to the next question and resets the submission state."""
    st.session_state.current_index += 1
    st.session_state.submitted = False
    st.rerun() 

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
            st.rerun()
        else:
            st.error("Fetched questions were empty or corrupted. Please try again.")
    else:
        pass 

def reset_quiz():
    """Resets the entire quiz session back to the settings screen."""
    if 'quiz_started' in st.session_state:
        del st.session_state['quiz_started']
    
    st.session_state.current_index = 0
    st.session_state.score = 0
    st.session_state.submitted = False
    st.session_state.score_submitted = False
    if 'questions_df' in st.session_state:
        del st.session_state['questions_df']
    if 'num_questions' in st.session_state:
        del st.session_state['num_questions']
    
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
        # Displaying a placeholder for structure if DB is offline
        df_placeholder = get_leaderboard_data(limit=0)
        st.table(df_placeholder)
        return
    
    with st.spinner('Loading top scores...'):
        df_leaderboard = get_leaderboard_data(limit=10)
    
    if not df_leaderboard.empty:
        st.dataframe(df_leaderboard, hide_index=True, use_container_width=True)
    else:
        st.info("No scores found yet! Be the first one to set a record.")


# --- 4. The Main App Function ---

def main():
    """The main Streamlit application function."""
    st.set_page_config(page_title="The Python Quiz Master", layout="centered", initial_sidebar_state="expanded")
    
    st.markdown("""
        <style>
            /* Custom CSS for a clean, dark, modern look */
            .css-1d3c0cr { padding-top: 2rem; } /* Reduce space above main content */
            .stButton>button { 
                border-radius: 12px; 
                transition: all 0.3s;
            }
            .stButton>button:hover {
                transform: scale(1.02);
            }
            .stAlert { border-radius: 12px; }
            
            /* Hiding Streamlit's default hamburger menu for a cleaner look */
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}

            /* Custom aesthetic for the dynamic welcome section */
            .welcome-box {
                background-color: #1f3b4d; /* Dark teal background */
                padding: 25px;
                border-radius: 15px;
                margin-top: 20px;
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.4);
                color: #e6f7ff;
            }
            .welcome-box h3 {
                color: #52c2c2; /* Bright teal for heading */
                margin-top: 0;
            }
        </style>
        """, unsafe_allow_html=True)
    
    st.title("🧠 The Python Quiz Master")
    st.markdown("---")

    if 'score_submitted' not in st.session_state:
        st.session_state.score_submitted = False
        
    selected_difficulty_name = next(
        (k for k, v in DIFFICULTY_OPTIONS.items() if v == st.session_state.get('selected_difficulty')), 
        list(DIFFICULTY_OPTIONS.keys())[0]
    )
    selected_category_name = next(
        (k for k, v in CATEGORY_OPTIONS.items() if v == st.session_state.get('selected_category')), 
        list(CATEGORY_OPTIONS.keys())[0]
    )


    # --- Quiz Settings Sidebar ---
    with st.sidebar:
        st.header("Quiz Settings")
        
        selected_difficulty = st.selectbox(
            "Select Difficulty:",
            list(DIFFICULTY_OPTIONS.keys()),
            index=list(DIFFICULTY_OPTIONS.keys()).index(selected_difficulty_name),
            key='difficulty_select'
        )
        st.session_state['selected_difficulty'] = DIFFICULTY_OPTIONS[selected_difficulty]

        selected_category = st.selectbox(
            "Select Topic/Subject:",
            list(CATEGORY_OPTIONS.keys()),
            index=list(CATEGORY_OPTIONS.keys()).index(selected_category_name),
            key='category_select'
        )
        st.session_state['selected_category'] = CATEGORY_OPTIONS[selected_category]
        
        st.button("Start New Quiz", on_click=start_quiz, type="primary", use_container_width=True)
        st.button("Reset App", on_click=reset_quiz, type="secondary", use_container_width=True)


    # --- Quiz Workflow ---
    if 'quiz_started' not in st.session_state or st.session_state.quiz_started is False:
        st.header("Welcome to the Ultimate MCQs Challenge!")
        st.subheader(f"Current Selections: {selected_category} | Difficulty: {selected_difficulty}")
        
        # --- FIX: Replaced placeholder image with dynamic welcome block ---
        st.markdown(
            f"""
            <div class="welcome-box">
                <h3>Ready to prove your genius?</h3>
                <p>🌎 Challenge yourself with fresh, real-time questions in **{selected_category}**.</p>
                <p>💪 Set your skill level to **{selected_difficulty}**.</p>
                <p>🥇 Rank on the Global Leaderboard!</p>
                <p>Click **'Start New Quiz'** on the left to begin your challenge!</p>
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
        
        st.markdown(f"**Topic:** `{selected_category}` | **Difficulty:** `{selected_difficulty}`")
        st.metric(label="Current Score", value=f"{score} / {num_questions}") 
        
        st.markdown(f"**Question {current_index + 1} of {num_questions}**")
        st.progress((current_index + 1) / num_questions)
        st.markdown("---")


        current_q = questions_df.iloc[current_index]
        
        question_text = current_q['question']
        options = current_q['options']
        correct_answer = current_q['answer']
        
        st.subheader(f"❓ {question_text}")

        with st.form(key=f'question_form_{current_index}'):
            user_choice = st.radio(
                "Select your answer:",
                options,
                index=None,
                key=f'radio_{current_index}'
            )
            
            submit_button = st.form_submit_button(
                label='Submit Answer', 
                disabled=st.session_state.submitted,
                type="secondary"
            )

        if submit_button and user_choice is not None:
            check_answer(user_choice, correct_answer)


    else:
        # --- Quiz Finished Screen ---
        st.balloons()
        st.header("🎉 Quiz Completed! Time to Check Your Rank.")
        final_score = st.session_state.score
        num_questions = st.session_state.num_questions
        
        percentage = (final_score / num_questions) * 100 if num_questions > 0 else 0

        st.metric(label="Final Score", value=f"{final_score} / {num_questions}", delta_color="off")
        st.metric(label="Percentage Correct", value=f"{percentage:.1f}%")
        
        st.markdown(f"**Topic:** `{selected_category}` | **Difficulty:** `{selected_difficulty}`")
        st.markdown("---")

        # --- Score Saving Section ---
        if st.session_state.score_submitted is False and st.session_state.get('db') is not None:
            difficulty_name = selected_difficulty
            category_name = selected_category
            
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
        st.button("Start New Quiz (Go to Settings)", on_click=reset_quiz, type="secondary")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error("An error occurred during application startup. Please check the console.")
        st.code(f"Error: {e}")