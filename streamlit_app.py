
import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from openai import OpenAI
import json
import uuid
import re
from datetime import datetime, timezone


# ==========================================
# 1. APPLICATION CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Personal AI Ecosystem",
    page_icon="🧠",
    layout="wide"
)

st.title("Personal AI Ecosystem")
st.caption("An AI assistant with persistent memory")


# ==========================================
# 2. INITIALIZE CONNECTIONS
# ==========================================

@st.cache_resource
def initialize_connections():

    # OpenAI
    client = OpenAI(
        api_key=st.secrets["openai"]["api_key"]
    )

    # Firebase
    firebase_config = dict(
        st.secrets["firebase"]["service_account"]
    )

    if not firebase_admin._apps:
        firebase_cred = credentials.Certificate(
            firebase_config
        )

        firebase_admin.initialize_app(
            firebase_cred,
            {
                "databaseURL":
                st.secrets["firebase"]["database_url"]
            }
        )

    memory_ref = db.reference(
        "ai_ecosystem/memories"
    )

    return client, memory_ref


try:
    client, memory_ref = initialize_connections()
    st.sidebar.success("AI and Firebase connected")

except Exception as e:
    st.error(f"Connection error: {e}")
    st.stop()


# ==========================================
# 3. MEMORY MANAGEMENT
# ==========================================

def save_memory(title, category, content, tags, source):

    memory_id = str(uuid.uuid4())

    memory = {
        "title": title,
        "category": category,
        "content": content,
        "tags": tags,
        "source": source,
        "status": "active",
        "created_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    memory_ref.child(memory_id).set(memory)

    return memory_id


def retrieve_memories(query, limit=5):

    memories = memory_ref.get()

    if not memories:
        return []

    # Extract keywords
    keywords = set(
        re.findall(r"\w+", query.lower())
    )

    results = []

    for memory_id, memory in memories.items():

        if memory.get("status") != "active":
            continue

        searchable = " ".join([
            memory.get("title", ""),
            memory.get("category", ""),
            memory.get("content", ""),
            " ".join(memory.get("tags", []))
        ]).lower()

        searchable_words = set(
            re.findall(r"\w+", searchable)
        )

        score = len(keywords & searchable_words)

        if score > 0:
            results.append({
                "id": memory_id,
                "score": score,
                **memory
            })

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return results[:limit]


# ==========================================
# 4. AI RESPONSE GENERATION
# ==========================================

def generate_response(user_message):

    memories = retrieve_memories(user_message)

    memory_context = json.dumps(
        memories,
        ensure_ascii=False
    )

    system_prompt = f"""
You are an AI assistant with access to a
persistent external memory database.

RETRIEVED MEMORIES:
{memory_context}

INSTRUCTIONS:

1. Answer the user's question naturally.
2. Use retrieved memories when relevant.
3. Do not invent memories or personal facts.
4. Do not claim to remember something
   that is not present in the retrieved data.
5. Identify potentially useful information
   that could be saved for future conversations.
6. Do not suggest saving sensitive personal
   information.
7. Never save anything yourself.

Return a JSON object with this structure:

{{
    "reply": "Your response to the user",
    "suggestion": null
}}

If useful information is identified, suggestion
should instead contain:

{{
    "title": "Short memory title",
    "category": "Category",
    "content": "Information to remember",
    "tags": ["tag1", "tag2"]
}}

Only suggest information that is reasonably
useful beyond the current conversation.
Do not suggest temporary or trivial details.
"""

    response = client.responses.create(
        model=st.secrets["openai"]["model"],
        instructions=system_prompt,
        input=user_message,
        text={
            "format": {
                "type": "json_object"
            }
        }
    )

    result = json.loads(response.output_text)

    return result


# ==========================================
# 5. SESSION STATE
# ==========================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_suggestion" not in st.session_state:
    st.session_state.pending_suggestion = None

if "review_mode" not in st.session_state:
    st.session_state.review_mode = False


# ==========================================
# 6. SIDEBAR - MANUAL MEMORY
# ==========================================

st.sidebar.header("Memory Management")

with st.sidebar.expander(
    "Add Memory Manually",
    expanded=False
):

    with st.form("manual_memory_form"):

        title = st.text_input("Memory Title")

        category = st.selectbox(
            "Category",
            [
                "Personal Information",
                "Projects",
                "Preferences",
                "Knowledge",
                "Other"
            ]
        )

        content = st.text_area(
            "Information to Remember"
        )

        tags = st.text_input(
            "Tags (separate with commas)"
        )

        submitted = st.form_submit_button(
            "Save Memory"
        )

        if submitted:

            if title.strip() and content.strip():

                try:
                    save_memory(
                        title,
                        category,
                        content,
                        [
                            tag.strip()
                            for tag in tags.split(",")
                            if tag.strip()
                        ],
                        "manual"
                    )

                    st.success("Memory saved!")

                except Exception as e:
                    st.error(f"Save failed: {e}")

            else:
                st.warning("Please complete the required fields.")


# ==========================================
# 7. MEMORY VIEWER
# ==========================================

with st.sidebar.expander("View Stored Memories"):

    try:
        all_memories = memory_ref.get() or {}

        if not all_memories:
            st.info("No memories stored yet.")

        for memory_id, memory in all_memories.items():

            if memory.get("status") != "active":
                continue

            st.markdown(
                f"**{memory.get('title', 'Untitled')}**"
            )

            st.caption(
                memory.get("category", "Other")
            )

            st.write(
                memory.get("content", "")
            )

            st.divider()

    except Exception as e:
        st.error(f"Unable to load memories: {e}")


# ==========================================
# 8. DISPLAY CHAT HISTORY
# ==========================================

for message in st.session_state.messages:

    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# ==========================================
# 9. CHAT INPUT
# ==========================================

user_message = st.chat_input(
    "Talk to your AI...",
    disabled=bool(
        st.session_state.pending_suggestion
    )
)

if user_message:

    st.session_state.messages.append({
        "role": "user",
        "content": user_message
    })

    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):

        with st.spinner("Thinking..."):

            try:
                result = generate_response(
                    user_message
                )

                reply = result.get(
                    "reply",
                    "I couldn't generate a response."
                )

                st.markdown(reply)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": reply
                })

                suggestion = result.get("suggestion")

                if isinstance(suggestion, dict):
                    st.session_state.pending_suggestion = (
                        suggestion
                    )

            except Exception as e:

                st.error(f"AI error: {e}")

    st.rerun()


# ==========================================
# 10. MEMORY SUGGESTION SYSTEM
# ==========================================

suggestion = st.session_state.pending_suggestion

if suggestion:

    st.divider()
    st.subheader("AI Memory Suggestion")

    st.write(
        "I identified some information that "
        "might be useful to remember."
    )

    st.info(
        f"**{suggestion.get('title', 'Untitled')}**\n\n"
        f"{suggestion.get('content', '')}"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        if st.button(
            "Approve",
            type="primary",
            use_container_width=True
        ):

            try:
                save_memory(
                    suggestion.get("title", "Untitled"),
                    suggestion.get("category", "Other"),
                    suggestion.get("content", ""),
                    suggestion.get("tags", []),
                    "ai_suggestion"
                )

                st.session_state.pending_suggestion = None
                st.success("Memory saved!")
                st.rerun()

            except Exception as e:
                st.error(f"Save failed: {e}")

    with col2:

        if st.button(
            "Reject",
            use_container_width=True
        ):

            st.session_state.pending_suggestion = None
            st.rerun()

    with col3:

        if st.button(
            "I wish to choose this",
            use_container_width=True
        ):

            st.session_state.review_mode = True
            st.rerun()


# ==========================================
# 11. MANUAL MEMORY REVIEW
# ==========================================

if (
    st.session_state.review_mode
    and st.session_state.pending_suggestion
):

    suggestion = st.session_state.pending_suggestion

    st.divider()
    st.subheader("Review Memory Before Saving")

    with st.form("review_memory_form"):

        edited_title = st.text_input(
            "Title",
            value=suggestion.get("title", "")
        )

        edited_category = st.text_input(
            "Category",
            value=suggestion.get("category", "Other")
        )

        edited_content = st.text_area(
            "Content",
            value=suggestion.get("content", "")
        )

        edited_tags = st.text_input(
            "Tags",
            value=", ".join(
                suggestion.get("tags", [])
            )
        )

        save_button = st.form_submit_button(
            "Save Edited Memory"
        )

        if save_button:

            if edited_title.strip() and edited_content.strip():

                try:
                    save_memory(
                        edited_title,
                        edited_category,
                        edited_content,
                        [
                            tag.strip()
                            for tag in edited_tags.split(",")
                            if tag.strip()
                        ],
                        "manual_review"
                    )

                    st.session_state.pending_suggestion = None
                    st.session_state.review_mode = False

                    st.success("Edited memory saved!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Save failed: {e}")

            else:
                st.warning("Title and content are required.")

    if st.button("Cancel Review"):

        st.session_state.review_mode = False
        st.rerun()
